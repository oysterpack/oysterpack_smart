import asyncio
import logging
import unittest
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from ssl import SSLCertVerificationError
from typing import Iterable, AsyncIterable, cast, Self, ClassVar

import msgpack  # type: ignore
from algosdk.account import generate_account
from algosdk.transaction import Transaction, Multisig
from beaker import sandbox
from beaker.consts import algo
from websockets.legacy.client import connect

from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.client.model import MicroAlgos
from oysterpack.algorand.client.transactions import payment
from oysterpack.algorand.messaging.secure_message import (
    SignedEncryptedMessage,
    create_secure_message,
    unpack_secure_message,
)
from oysterpack.algorand.messaging.secure_message_client import SecureMessageClient
from oysterpack.algorand.messaging.secure_message_handler import (
    SecureMessageHandler,
    MessageContext,
    SecureMessageWebsocketHandler,
    MessageHandlerMapping,
    SecureMessageHandlerError,
    SecureMessageHandlerErrorCode,
)
from oysterpack.algorand.messaging.websocket import Data
from oysterpack.core.message import (
    Message,
    MessageType,
    MessageId,
    Serializable,
    SignedMessage,
    MultisigMessage,
)
from oysterpack.services.asyncio.websockets_server import WebsocketsServer
from tests.algorand.messaging import server_ssl_context, client_ssl_context
from tests.test_support import OysterPackIsolatedAsyncioTestCase

logger = logging.getLogger("SecureMessageHandlerTestCase")


@dataclass(slots=True)
class Request(Serializable):
    MSG_TYPE: ClassVar[MessageType] = MessageType.from_str("01GVH1J2JQ4A8SR03MTXG3VMZY")

    request_id: MessageId

    txns: list[Transaction]

    @classmethod
    def message_type(cls) -> MessageType:
        return cls.MSG_TYPE

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        request_id, txns = msgpack.unpackb(packed, use_list=False)
        return cls(
            request_id=MessageId.from_bytes(request_id),
            txns=[Transaction.undictify(txn) for txn in txns],
        )

    @classmethod
    def from_message(cls, msg: Message) -> Self:
        if msg.msg_type != Request.MSG_TYPE:
            raise ValueError("invalid message type")

        return Self.unpackb(msg.data)  # type: ignore

    def pack(self) -> bytes:
        return msgpack.packb(
            (
                self.request_id.bytes,
                [txn.dictify() for txn in self.txns],
            )
        )

    def to_message(self) -> Message:
        return Message(
            msg_id=self.request_id,
            msg_type=Request.MSG_TYPE,
            data=self.pack(),
        )


async def echo_message_handler(ctx: MessageContext):
    logger.info("echo_message_handler: START")
    response = await ctx.pack_secure_message(Request.unpack(ctx.msg_data))
    logger.info("echo_message_handler: packed response")
    await ctx.websocket.send(response)
    logger.info("echo_message_handler: sent response")


class WebsocketMock:
    def __init__(self) -> None:
        self.request_queue: asyncio.Queue[Data] = asyncio.Queue()
        self.response_queue: asyncio.Queue[Data] = asyncio.Queue()

    async def recv(self) -> Data:
        msg = await self.request_queue.get()
        self.request_queue.task_done()
        return msg

    async def send(
        self,
        message: Data | Iterable[Data] | AsyncIterable[Data],
    ) -> None:
        await self.response_queue.put(cast(Data, message))


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
            message_handlers=(
                MessageHandlerMapping(
                    msg_handler=echo_message_handler,
                    msg_types={Request.message_type()},
                ),
            ),
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
            message_handlers=(
                MessageHandlerMapping(
                    msg_handler=echo_message_handler,
                    msg_types={Request.message_type()},
                ),
            ),
            executor=self.executor,
        )
        ws = WebsocketMock()

        secure_message.encrypted_msg.encrypted_msg += b"1"

        # Act
        await handle_message(secure_message, ws)

        # Assert
        response_bytes = await ws.response_queue.get()
        ws.response_queue.task_done()
        self.assertIsInstance(response_bytes, bytes)
        logger.info("len(response_bytes)= %s", len(response_bytes))

        # response should be a SecureMessage
        response_msg = unpack_secure_message(self.sender_private_key, response_bytes)
        self.assertEqual(
            SecureMessageHandlerError.message_type(), response_msg.msg_type
        )
        err = SecureMessageHandlerError.unpack(response_msg.data)
        logger.info(err)
        self.assertEqual(
            SecureMessageHandlerErrorCode.SIGNATURE_VERIFICATION_FAILED, err.err_code
        )

    async def test_init(self):
        with self.subTest("no message handlers specified"):
            with self.assertRaises(ValueError) as err:
                SecureMessageHandler(
                    private_key=self.recipient_private_key,
                    message_handlers=(),
                    executor=self.executor,
                )

        with self.subTest("duplicate MessageTypes registered"):
            with self.assertRaises(ValueError) as err:
                SecureMessageHandler(
                    private_key=self.recipient_private_key,
                    message_handlers=(
                        MessageHandlerMapping(
                            msg_handler=echo_message_handler,
                            msg_types={Request.message_type()},
                        ),
                        MessageHandlerMapping(
                            msg_handler=echo_message_handler,
                            msg_types={Request.message_type()},
                        ),
                    ),
                    executor=self.executor,
                )

    async def test_signed_message(self):
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

        signed_request = SignedMessage.sign(
            self.sender_private_key,
            request,
        )

        secure_message = create_secure_message(
            private_key=self.sender_private_key,
            data=signed_request,
            recipient=self.recipient_private_key.encryption_address,
        )

        handle_message = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=(
                MessageHandlerMapping(
                    msg_handler=echo_message_handler,
                    msg_types={Request.message_type()},
                ),
            ),
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

    async def test_signed_message_with_wrong_private_key(self):
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

        signed_request = SignedMessage.sign(
            AlgoPrivateKey(),
            request,
        )
        # change the signer address to cause signature verification to fail
        signed_request.signer = AlgoPrivateKey().signing_address

        secure_message = create_secure_message(
            private_key=self.sender_private_key,
            data=signed_request,
            recipient=self.recipient_private_key.encryption_address,
        )

        handle_message = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=(
                MessageHandlerMapping(
                    msg_handler=echo_message_handler,
                    msg_types={Request.message_type()},
                ),
            ),
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
        response_msg = unpack_secure_message(self.sender_private_key, response_bytes)
        self.assertEqual(
            SecureMessageHandlerError.message_type(), response_msg.msg_type
        )
        err = SecureMessageHandlerError.unpack(response_msg.data)
        logger.info(err)
        self.assertEqual(
            SecureMessageHandlerErrorCode.SIGNATURE_VERIFICATION_FAILED, err.err_code
        )

    async def test_multisig_message(self):
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

        signer_1 = AlgoPrivateKey()
        signer_2 = AlgoPrivateKey()
        multisig = Multisig(
            version=1,
            threshold=2,
            addresses=[
                signer_1.signing_address,
                signer_2.signing_address,
            ],
        )
        signed_request = MultisigMessage.create(
            multisig,
            request,
        )
        signed_request.sign(signer_1)
        signed_request.sign(signer_2)

        secure_message = create_secure_message(
            private_key=self.sender_private_key,
            data=signed_request,
            recipient=self.recipient_private_key.encryption_address,
        )

        handle_message = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=(
                MessageHandlerMapping(
                    msg_handler=echo_message_handler,
                    msg_types={Request.message_type()},
                ),
            ),
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

    async def test_multisig_message_with_wrong_private_key(self):
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

        signer_1 = AlgoPrivateKey()
        signer_2 = AlgoPrivateKey()
        multisig = Multisig(
            version=1,
            threshold=2,
            addresses=[
                signer_1.signing_address,
                signer_2.signing_address,
            ],
        )
        signed_request = MultisigMessage.create(
            multisig,
            request,
        )
        signed_request.sign(signer_1)
        signed_request.sign(signer_2)
        # change the signer address to cause signature verification to fail
        signed_request.multisig.subsigs[0].public_key = bytes(
            AlgoPrivateKey().public_key
        )

        secure_message = create_secure_message(
            private_key=self.sender_private_key,
            data=signed_request,
            recipient=self.recipient_private_key.encryption_address,
        )

        handle_message = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=(
                MessageHandlerMapping(
                    msg_handler=echo_message_handler,
                    msg_types={Request.message_type()},
                ),
            ),
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
        response_msg = unpack_secure_message(self.sender_private_key, response_bytes)
        self.assertEqual(
            SecureMessageHandlerError.message_type(), response_msg.msg_type
        )
        err = SecureMessageHandlerError.unpack(response_msg.data)
        logger.info(err)
        self.assertEqual(
            SecureMessageHandlerErrorCode.SIGNATURE_VERIFICATION_FAILED, err.err_code
        )


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
            message_handlers=(
                MessageHandlerMapping(
                    echo_message_handler,
                    {Request.message_type()},
                ),
            ),
            executor=self.executor,
        )

        websocket_handler = SecureMessageWebsocketHandler(
            handler=secure_message_handler
        )

        ws_server = WebsocketsServer(
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
                    data = Request.unpack(response.data)
                    self.assertEqual(request, data)

        with self.subTest(
            "SSLContext with server CA cert is required to connect via TLS"
        ):
            with self.assertRaises(SSLCertVerificationError):
                await connect(f"wss://localhost:{ws_server.port}")

        await ws_server.stop()
        await ws_server.await_stopped()


if __name__ == "__main__":
    unittest.main()
