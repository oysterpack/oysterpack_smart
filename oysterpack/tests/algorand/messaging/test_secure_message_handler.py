import asyncio
import logging
import unittest
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from ssl import SSLCertVerificationError
from typing import Iterable, AsyncIterable, cast, Final, Self

import msgpack  # type: ignore
from algosdk.account import generate_account
from algosdk.transaction import Transaction
from beaker import sandbox
from beaker.consts import algo
from websockets.legacy.client import connect

from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.client.model import MicroAlgos
from oysterpack.algorand.client.transactions import payment
from oysterpack.algorand.messaging.secure_message import (
    SignedEncryptedMessage,
    create_secure_message,
)
from oysterpack.algorand.messaging.secure_message_client import SecureMessageClient
from oysterpack.algorand.messaging.secure_message_handler import (
    SecureMessageHandler,
    MessageContext,
    SecureMessageWebsocketHandler,
)
from oysterpack.algorand.messaging.websocket import Data
from oysterpack.core.message import Message, MessageType, MessageId, Serializable
from oysterpack.services.asyncio.websockets_server import WebsocketsServer
from tests.algorand.messaging import server_ssl_context, client_ssl_context
from tests.test_support import OysterPackIsolatedAsyncioTestCase

logger = logging.getLogger("SecureMessageHandlerTestCase")

REQUEST_MSG_TYPE: Final[MessageType] = MessageType.from_str(
    "01GVH1J2JQ4A8SR03MTXG3VMZY"
)


@dataclass(slots=True)
class Request(Serializable):
    request_id: MessageId

    txns: list[Transaction]

    @staticmethod
    def message_type() -> MessageType:
        return REQUEST_MSG_TYPE

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        request_id, txns = msgpack.unpackb(packed, use_list=False)
        return cls(
            request_id=MessageId.from_bytes(request_id),
            txns=[Transaction.undictify(txn) for txn in txns],
        )

    @classmethod
    def from_message(cls, msg: Message) -> Self:
        if msg.msg_type != REQUEST_MSG_TYPE:
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
            msg_type=REQUEST_MSG_TYPE,
            data=self.pack(),
        )


async def echo_message_handler(ctx: MessageContext):
    logger.info("echo_message_handler: START")
    response = await ctx.pack_secure_message(Request.unpack(ctx.msg.data))
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
            message_handlers=((echo_message_handler, (Request.message_type(),)),),
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
        decrypted_response_msg_bytes = response.secret_msg.decrypt(
            self.sender_private_key
        )
        # request should have been echoed back
        decrypted_response_msg = Message.unpack(decrypted_response_msg_bytes)
        request_2 = Request.unpack(decrypted_response_msg.data)
        self.assertEqual(request, request_2)


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
            message_handlers=((echo_message_handler, (Request.message_type(),)),),
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
