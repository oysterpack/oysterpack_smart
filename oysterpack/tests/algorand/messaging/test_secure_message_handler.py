import asyncio
import logging
import unittest
from dataclasses import dataclass
from typing import Iterable, AsyncIterable, cast, Final, Self

import msgpack  # type: ignore
from algosdk.account import generate_account
from algosdk.transaction import Transaction
from beaker import sandbox
from beaker.consts import algo

from oysterpack.algorand.client.accounts.private_key import AlgoPrivateKey
from oysterpack.algorand.client.model import MicroAlgos
from oysterpack.algorand.client.transactions import payment
from oysterpack.algorand.messaging.secure_message_handler import (
    SecureMessageHandler,
    MessageContext,
    pack_secure_message,
)
from oysterpack.algorand.messaging.websocket import Data
from oysterpack.core.message import Message, MessageType, MessageId
from tests.test_support import OysterPackIsolatedAsyncioTestCase

logger = logging.getLogger("SecureMessageHandlerTestCase")

REQUEST_MSG_TYPE: Final[MessageType] = MessageType.from_str(
    "01GVH1J2JQ4A8SR03MTXG3VMZY"
)


@dataclass(slots=True)
class Request:
    id: MessageId

    txns: list[Transaction]

    @staticmethod
    def message_type() -> MessageType:
        return REQUEST_MSG_TYPE

    @classmethod
    def unpackb(cls, packed: bytes) -> "Request":
        id, txns = msgpack.unpackb(packed, use_list=False)
        return cls(
            id=MessageId.from_bytes(id),
            txns=[Transaction.undictify(txn) for txn in txns],
        )

    @classmethod
    def from_message(cls, msg: Message) -> Self:  # type: ignore
        if msg.type != REQUEST_MSG_TYPE:
            raise ValueError("invalid message type")

        return Self.unpackb(msg.data)  # type: ignore

    def packb(self) -> bytes:
        return msgpack.packb((self.id.bytes, [txn.dictify() for txn in self.txns]))

    def to_message(self) -> Message:
        return Message(
            id=self.id,
            type=REQUEST_MSG_TYPE,
            data=self.packb(),
        )


@dataclass(slots=True)
class Response:
    id: MessageId

    def packb(self) -> bytes:
        return msgpack.packb((self.id.bytes))


async def echo_message_handler(ctx: MessageContext):
    logger.info("echo_message_handler: START")
    response = await ctx.pack_secure_message_bytes(lambda: ctx.msg)
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
    def setUp(self) -> None:
        self.sender_private_key = AlgoPrivateKey(generate_account()[0])
        self.recipient_private_key = AlgoPrivateKey(generate_account()[0])

    async def test_message_handling(self):
        # SETUP
        request = Request(
            id=MessageId(),
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

        # run pack_secure_message in a separate thread to revent the event loop from being blocked
        secure_message = await asyncio.to_thread(
            pack_secure_message,
            sender_private_key=self.sender_private_key,
            msg=request.to_message(),
            recipient=self.recipient_private_key.encryption_address,
        )

        handle_message = SecureMessageHandler(
            private_key=self.recipient_private_key,
            message_handlers=((echo_message_handler, (Request.message_type(),)),),
        )
        ws = WebsocketMock()

        # Act
        await handle_message(secure_message, ws)
        response_bytes = await ws.response_queue.get()
        ws.response_queue.task_done()
        self.assertIsInstance(response_bytes, bytes)
        logger.info("len(response_bytes)= %s", len(response_bytes))


if __name__ == "__main__":
    unittest.main()
