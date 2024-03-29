import asyncio
import logging
import unittest
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta
from ssl import SSLCertVerificationError
from typing import Self, ClassVar

import msgpack  # type: ignore
from algosdk.account import generate_account
from algosdk.transaction import Transaction
from beaker import sandbox
from beaker.consts import algo
from websockets.exceptions import ConnectionClosedOK
from websockets.legacy.client import connect

from oysterpack.algorand.client.accounts.private_key import (
    AlgoPrivateKey,
    EncryptionAddress,
)
from oysterpack.algorand.client.model import MicroAlgos
from oysterpack.algorand.client.transactions import payment
from oysterpack.algorand.messaging.secure_message import (
    SignedEncryptedMessage,
    create_secure_message,
    EncryptedMessage,
)
from oysterpack.algorand.messaging.secure_message_client import SecureMessageClient
from oysterpack.algorand.messaging.secure_message_handler import (
    SecureMessageHandler,
    MessageContext,
    SecureMessageWebsocketHandler,
    MessageHandler,
)
from oysterpack.algorand.messaging.websocket import CloseCode
from oysterpack.core.message import (
    Message,
    MessageType,
    MessageId,
    Serializable,
)
from tests.algorand.messaging import server_ssl_context, client_ssl_context
from tests.support.websockets import WebsocketMock, create_websocket_server
from tests.test_support import OysterPackIsolatedAsyncioTestCase

logger = logging.getLogger("SecureMessageHandlerTestCase")


@dataclass(slots=True)
class Request(Serializable):
    MSG_TYPE: ClassVar[MessageType] = MessageType.from_str("01GVH1J2JQ4A8SR03MTXG3VMZY")

    request_id: MessageId

    txns: list[Transaction]

    fail: bool = False

    sleep: timedelta | None = None

    @classmethod
    def message_type(cls) -> MessageType:
        return cls.MSG_TYPE

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        request_id, txns, fail, sleep = msgpack.unpackb(packed, use_list=False)
        return cls(
            request_id=MessageId.from_bytes(request_id),
            txns=[Transaction.undictify(txn) for txn in txns],
            fail=fail,
            sleep=timedelta(microseconds=sleep) if sleep else None,
        )

    def pack(self) -> bytes:
        return msgpack.packb(
            (
                self.request_id.bytes,
                [txn.dictify() for txn in self.txns],
                self.fail,
                self.sleep.microseconds if self.sleep is not None else None,
            )
        )


class EchoMessageHandler(MessageHandler):
    def __init__(self, supported_msg_type: MessageType | None = None):
        self._supported_msg_type = (
            supported_msg_type if supported_msg_type else Request.message_type()
        )

    async def __call__(self, ctx: MessageContext):
        logger.info("echo_message_handler: received message type: %s", ctx.msg_type)

        assert Request.message_type() == ctx.msg_type

        request = Request.unpack(ctx.msg_data)
        if request.sleep:
            await asyncio.sleep(float(request.sleep.microseconds) / 10**6)
        if request.fail:
            raise Exception("BOOM!")

        response = await ctx.pack_secure_message(ctx.msg.msg_id, request)
        logger.info("echo_message_handler: packed response")
        await ctx.websocket.send(response)
        logger.info("echo_message_handler: sent response")

    def supported_msg_types(self) -> set[MessageType]:
        return {self._supported_msg_type}


class SecureMessageHandlerTestCase(OysterPackIsolatedAsyncioTestCase):
    executor: ProcessPoolExecutor

    @classmethod
    def setUpClass(cls) -> None:
        cls.executor = ProcessPoolExecutor()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.executor.shutdown()

    def setUp(self) -> None:
        self.sender_private_key = AlgoPrivateKey(generate_account()[0])
        self.recipient_private_key = AlgoPrivateKey(generate_account()[0])

    async def test_message_handling(self):
        # SETUP
        request = Request(
            request_id=MessageId(),
            txns=[
                payment.transfer_algo(
                    sender=self.sender_private_key.signing_address,
                    receiver=self.recipient_private_key.signing_address,
                    amount=MicroAlgos(1 * algo),
                    suggested_params=sandbox.get_algod_client().suggested_params(),
                ),
                payment.transfer_algo(
                    sender=self.sender_private_key.signing_address,
                    receiver=self.recipient_private_key.signing_address,
                    amount=MicroAlgos(10 * algo),
                    suggested_params=sandbox.get_algod_client().suggested_params(),
                ),
            ],
        )

        secure_message = create_secure_message(
            private_key=self.sender_private_key,
            data=request,
            recipient=self.recipient_private_key.encryption_address,
        )

        handle_message = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=[EchoMessageHandler()],
            executor=self.executor,
        )
        ws = WebsocketMock()

        # Act
        await handle_message(secure_message, ws)

        # Assert
        response_bytes = await ws.response_queue.get()
        ws.response_queue.task_done()
        self.assertIsInstance(response_bytes, bytes)
        logger.info("len(response_bytes)= %s", len(response_bytes))

        # response should be a SecureMessage
        response = SignedEncryptedMessage.unpack(response_bytes)
        logger.info(response)
        self.assertTrue(
            response.verify(), "SecureMessage signature verification failed"
        )
        self.assertEqual(self.recipient_private_key.signing_address, response.sender)
        decrypted_response_msg_bytes = response.encrypted_msg.decrypt(
            self.sender_private_key
        )
        # request should have been echoed back
        decrypted_response_msg = Message.unpack(decrypted_response_msg_bytes)
        request_2 = Request.unpack(decrypted_response_msg.data)
        self.assertEqual(request, request_2)

    async def test_invalid_message(self):
        # SETUP
        request = Request(
            request_id=MessageId(),
            txns=[
                payment.transfer_algo(
                    sender=self.sender_private_key.signing_address,
                    receiver=self.recipient_private_key.signing_address,
                    amount=MicroAlgos(1 * algo),
                    suggested_params=sandbox.get_algod_client().suggested_params(),
                ),
                payment.transfer_algo(
                    sender=self.sender_private_key.signing_address,
                    receiver=self.recipient_private_key.signing_address,
                    amount=MicroAlgos(10 * algo),
                    suggested_params=sandbox.get_algod_client().suggested_params(),
                ),
            ],
        )

        secure_message = create_secure_message(
            private_key=self.sender_private_key,
            data=request,
            recipient=self.recipient_private_key.encryption_address,
        )

        handle_message = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=[EchoMessageHandler()],
            executor=self.executor,
        )
        ws = WebsocketMock()

        secure_message.encrypted_msg.encrypted_msg += b"1"

        # Act
        await handle_message(secure_message, ws)

        # Assert
        self.assertTrue(ws.closed)
        self.assertEqual(CloseCode.GOING_AWAY, ws.close_code)
        self.assertEqual("invalid message", ws.close_reason)

    async def test_decryption_failure(self):
        # SETUP
        request = Request(
            request_id=MessageId(),
            txns=[
                payment.transfer_algo(
                    sender=self.sender_private_key.signing_address,
                    receiver=self.recipient_private_key.signing_address,
                    amount=MicroAlgos(1 * algo),
                    suggested_params=sandbox.get_algod_client().suggested_params(),
                ),
            ],
        )

        def create_secure_message(
            private_key: AlgoPrivateKey,
            data: Serializable,
            recipient: EncryptionAddress,
        ) -> SignedEncryptedMessage:
            msg = Message.create(data.message_type(), data.pack())
            secret_message = EncryptedMessage.encrypt(
                sender_private_key=private_key,
                recipient=recipient,
                msg=msg.pack(),
            )
            secret_message.encrypted_msg += b"1"
            return SignedEncryptedMessage.sign(
                private_key=private_key,
                msg=secret_message,
            )

        secure_message = create_secure_message(
            private_key=self.sender_private_key,
            data=request,
            recipient=self.recipient_private_key.encryption_address,
        )

        handle_message = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=[EchoMessageHandler()],
            executor=self.executor,
        )
        ws = WebsocketMock()

        # Act
        await handle_message(secure_message, ws)

        # Assert
        self.assertTrue(ws.closed)
        self.assertEqual(CloseCode.GOING_AWAY, ws.close_code)
        self.assertEqual("invalid message", ws.close_reason)

    async def test_message_unpacking_error(self):
        # SETUP
        request = Request(
            request_id=MessageId(),
            txns=[
                payment.transfer_algo(
                    sender=self.sender_private_key.signing_address,
                    receiver=self.recipient_private_key.signing_address,
                    amount=MicroAlgos(1 * algo),
                    suggested_params=sandbox.get_algod_client().suggested_params(),
                ),
            ],
        )

        def create_secure_message(
            private_key: AlgoPrivateKey,
            data: Serializable,
            recipient: EncryptionAddress,
        ) -> SignedEncryptedMessage:
            msg = Message.create(data.message_type(), data.pack())
            secret_message = EncryptedMessage.encrypt(
                sender_private_key=private_key,
                recipient=recipient,
                msg=msg.pack() + b"1",
            )
            return SignedEncryptedMessage.sign(
                private_key=private_key,
                msg=secret_message,
            )

        secure_message = create_secure_message(
            private_key=self.sender_private_key,
            data=request,
            recipient=self.recipient_private_key.encryption_address,
        )

        handle_message = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=[EchoMessageHandler()],
            executor=self.executor,
        )
        ws = WebsocketMock()

        # Act
        await handle_message(secure_message, ws)

        # Assert
        self.assertTrue(ws.closed)
        self.assertEqual(CloseCode.GOING_AWAY, ws.close_code)
        self.assertEqual("invalid message", ws.close_reason)

    async def test_init(self):
        with self.subTest("no message handlers specified"):
            with self.assertRaises(ValueError):
                SecureMessageHandler(
                    private_key=self.recipient_private_key,
                    message_handlers=[],
                    executor=self.executor,
                )

        with self.subTest("duplicate MessageTypes registered"):
            with self.assertRaises(ValueError):
                SecureMessageHandler(
                    private_key=self.recipient_private_key,
                    message_handlers=[EchoMessageHandler(), EchoMessageHandler()],
                    executor=self.executor,
                )

    async def test_unsupported_message(self):
        # SETUP
        request = Request(
            request_id=MessageId(),
            txns=[
                payment.transfer_algo(
                    sender=self.sender_private_key.signing_address,
                    receiver=self.recipient_private_key.signing_address,
                    amount=MicroAlgos(1 * algo),
                    suggested_params=sandbox.get_algod_client().suggested_params(),
                ),
                payment.transfer_algo(
                    sender=self.sender_private_key.signing_address,
                    receiver=self.recipient_private_key.signing_address,
                    amount=MicroAlgos(10 * algo),
                    suggested_params=sandbox.get_algod_client().suggested_params(),
                ),
            ],
        )

        secure_message = create_secure_message(
            private_key=self.sender_private_key,
            data=request,
            recipient=self.recipient_private_key.encryption_address,
        )

        handle_message = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=[EchoMessageHandler(supported_msg_type=MessageType())],
            executor=self.executor,
        )
        ws = WebsocketMock()

        # Act
        await handle_message(secure_message, ws)
        await asyncio.sleep(0)

        # Assert
        self.assertTrue(ws.closed)
        self.assertEqual(CloseCode.GOING_AWAY, ws.close_code)
        self.assertEqual("unsupported msg type", ws.close_reason)


class SecureMessageWebsocketHandlerTestCase(OysterPackIsolatedAsyncioTestCase):
    executor: ProcessPoolExecutor

    @classmethod
    def setUpClass(cls) -> None:
        cls.executor = ProcessPoolExecutor()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.executor.shutdown()

    def setUp(self) -> None:
        self.sender_private_key = AlgoPrivateKey(generate_account()[0])
        self.recipient_private_key = AlgoPrivateKey(generate_account()[0])

    async def test_websocket_server(self):
        # SETUP
        request = Request(
            request_id=MessageId(),
            txns=[
                payment.transfer_algo(
                    sender=self.sender_private_key.signing_address,
                    receiver=self.recipient_private_key.signing_address,
                    amount=MicroAlgos(1 * algo),
                    suggested_params=sandbox.get_algod_client().suggested_params(),
                ),
                payment.transfer_algo(
                    sender=self.sender_private_key.signing_address,
                    receiver=self.recipient_private_key.signing_address,
                    amount=MicroAlgos(10 * algo),
                    suggested_params=sandbox.get_algod_client().suggested_params(),
                ),
            ],
        )

        secure_message_handler = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=[EchoMessageHandler()],
            executor=self.executor,
        )

        websocket_handler = SecureMessageWebsocketHandler(
            handler=secure_message_handler
        )

        ws_server = create_websocket_server(
            handler=websocket_handler,
            ssl_context=server_ssl_context(),
        )
        await ws_server.start()
        await ws_server.await_running()
        await asyncio.sleep(0)

        with self.subTest("using ProcessPoolExecutor based SecureMessageClient"):
            async with connect(
                f"wss://localhost:{ws_server.port}",
                ssl=client_ssl_context(),
            ) as websocket:
                with ProcessPoolExecutor() as executor:
                    client = SecureMessageClient(
                        websocket=websocket,
                        private_key=self.sender_private_key,
                        executor=executor,
                    )
                    await client.send(
                        request,
                        self.recipient_private_key.encryption_address,
                    )
                    response = await client.recv()
                    await client.close()
                    data = Request.unpack(response.data)
                    self.assertEqual(request, data)

        with self.subTest("using ThreadPoolExecutor based SecureMessageClient"):
            async with connect(
                f"wss://localhost:{ws_server.port}",
                ssl=client_ssl_context(),
            ) as websocket:
                with ThreadPoolExecutor() as executor:
                    client = SecureMessageClient(
                        websocket=websocket,
                        private_key=self.sender_private_key,
                        executor=executor,
                    )
                    await client.send(
                        request, self.recipient_private_key.encryption_address
                    )
                    response = await client.recv()
                    await client.close()
                    data = Request.unpack(response.data)
                    self.assertEqual(request, data)

        with self.subTest(
            "SSLContext with server CA cert is required to connect via TLS"
        ):
            with self.assertRaises(SSLCertVerificationError):
                await connect(f"wss://localhost:{ws_server.port}")

        await ws_server.stop()
        await ws_server.await_stopped()

    async def test_throttling(self):
        # SETUP
        request = Request(
            request_id=MessageId(),
            txns=[
                payment.transfer_algo(
                    sender=self.sender_private_key.signing_address,
                    receiver=self.recipient_private_key.signing_address,
                    amount=MicroAlgos(1 * algo),
                    suggested_params=sandbox.get_algod_client().suggested_params(),
                ),
            ],
            sleep=timedelta(milliseconds=10),
        )

        secure_message_handler = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=[EchoMessageHandler()],
            executor=self.executor,
        )

        websocket_handler = SecureMessageWebsocketHandler(
            handler=secure_message_handler,
            max_concurrent_requests=1,
        )
        self.assertEqual(1, websocket_handler.max_concurrent_requests)

        ws_server = create_websocket_server(
            handler=websocket_handler, ssl_context=server_ssl_context()
        )
        await ws_server.start()
        await ws_server.await_running()
        await asyncio.sleep(0)

        async with connect(
            f"wss://localhost:{ws_server.port}",
            ssl=client_ssl_context(),
        ) as websocket:
            with ProcessPoolExecutor() as executor:
                client = SecureMessageClient(
                    websocket=websocket,
                    private_key=self.sender_private_key,
                    executor=executor,
                )
                tasks = []
                for _ in range(10):
                    task = asyncio.create_task(
                        client.send(
                            request,
                            self.recipient_private_key.encryption_address,
                        )
                    )
                    tasks.append(task)
                for _ in range(10):
                    response = await client.recv()
                    data = Request.unpack(response.data)
                    self.assertEqual(request, data)
                logger.info(websocket_handler.metrics)
                self.assertTrue(websocket_handler.metrics.throttle_count > 0)

        await ws_server.stop()
        await ws_server.await_stopped()

    async def test_handler_failure_with_throttling(self):
        # SETUP
        request = Request(
            request_id=MessageId(),
            txns=[
                payment.transfer_algo(
                    sender=self.sender_private_key.signing_address,
                    receiver=self.recipient_private_key.signing_address,
                    amount=MicroAlgos(1 * algo),
                    suggested_params=sandbox.get_algod_client().suggested_params(),
                ),
            ],
            fail=True,
        )

        secure_message_handler = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=[EchoMessageHandler()],
            executor=self.executor,
        )

        websocket_handler = SecureMessageWebsocketHandler(
            handler=secure_message_handler, max_concurrent_requests=1
        )

        ws_server = create_websocket_server(
            handler=websocket_handler,
            ssl_context=server_ssl_context(),
        )
        await ws_server.start()
        await ws_server.await_running()
        await asyncio.sleep(0)

        async with connect(
            f"wss://localhost:{ws_server.port}",
            ssl=client_ssl_context(),
        ) as websocket:
            with ProcessPoolExecutor() as executor:
                client = SecureMessageClient(
                    websocket=websocket,
                    private_key=self.sender_private_key,
                    executor=executor,
                )

                with self.assertRaises(ConnectionClosedOK) as err:
                    tasks = []
                    for _ in range(10):
                        task = asyncio.create_task(
                            client.send(
                                request,
                                self.recipient_private_key.encryption_address,
                            )
                        )
                        tasks.append(task)
                    await client.recv()
                logger.exception(err.exception)

        await ws_server.stop()
        await ws_server.await_stopped()

    async def test_handler_failure(self):
        # SETUP
        request = Request(
            request_id=MessageId(),
            txns=[
                payment.transfer_algo(
                    sender=self.sender_private_key.signing_address,
                    receiver=self.recipient_private_key.signing_address,
                    amount=MicroAlgos(1 * algo),
                    suggested_params=sandbox.get_algod_client().suggested_params(),
                ),
            ],
            fail=True,
        )

        secure_message_handler = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=[EchoMessageHandler()],
            executor=self.executor,
        )

        websocket_handler = SecureMessageWebsocketHandler(
            handler=secure_message_handler,
        )

        ws_server = create_websocket_server(
            handler=websocket_handler,
            ssl_context=server_ssl_context(),
        )
        await ws_server.start()
        await ws_server.await_running()
        await asyncio.sleep(0)

        async with connect(
            f"wss://localhost:{ws_server.port}",
            ssl=client_ssl_context(),
        ) as websocket:
            with ProcessPoolExecutor() as executor:
                client = SecureMessageClient(
                    websocket=websocket,
                    private_key=self.sender_private_key,
                    executor=executor,
                )
                await asyncio.create_task(
                    client.send(
                        request,
                        self.recipient_private_key.encryption_address,
                    )
                )
                with self.assertRaises(ConnectionClosedOK) as err:
                    await client.recv()
                logger.exception(err.exception)

        await ws_server.stop()
        await ws_server.await_stopped()

    async def test_invalid_msg(self):
        # SETUP
        secure_message_handler = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=[EchoMessageHandler()],
            executor=self.executor,
        )

        websocket_handler = SecureMessageWebsocketHandler(
            handler=secure_message_handler,
        )

        ws_server = create_websocket_server(
            handler=websocket_handler,
            ssl_context=server_ssl_context(),
        )
        await ws_server.start()
        await ws_server.await_running()
        await asyncio.sleep(0)

        # websocket connection should be closed when by the server when invalid messages are received
        with self.subTest("send str message"):
            async with connect(
                f"wss://localhost:{ws_server.port}",
                ssl=client_ssl_context(),
            ) as websocket:
                await websocket.send("request")
                with self.assertRaises(ConnectionClosedOK) as err:
                    await websocket.recv()
                logger.exception(err.exception)

        with self.subTest("send bytes message"):
            async with connect(
                f"wss://localhost:{ws_server.port}",
                ssl=client_ssl_context(),
            ) as websocket:
                await websocket.send(b"request")
                with self.assertRaises(ConnectionClosedOK) as err:
                    await websocket.recv()
                logger.exception(err.exception)

        await ws_server.stop()
        await ws_server.await_stopped()


if __name__ == "__main__":
    unittest.main()
