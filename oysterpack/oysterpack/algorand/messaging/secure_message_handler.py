"""
SecureMessage handler
"""
import asyncio
from abc import ABC
from dataclasses import dataclass
from typing import Final, Callable, Awaitable, Tuple
from uuid import UUID

import msgpack  # type: ignore
from nacl.exceptions import CryptoError
from ulid import ULID

from oysterpack.algorand.client.accounts.private_key import (
    AlgoPrivateKey,
    EncryptionAddress,
    SigningAddress,
)
from oysterpack.algorand.messaging.secure_message import SecureMessage, SecretMessage
from oysterpack.algorand.messaging.websocket import Websocket
from oysterpack.core.message import Message


class SecureMessageHandlerError(Exception):
    """
    SecureMessageHandler base exception
    """

    MSG_TYPE: Final[ULID] = ULID.from_str("01GVGS7ZK6WE9C3TDRBTVVAJ3J")

    def pack(self, msg_id: ULID | None = None) -> Message:
        """
        Serializes the exception into a Message
        """
        return Message(
            id=msg_id if msg_id else ULID(),
            type=self.MSG_TYPE,
            data=msgpack.packb((self.__class__.__name__, str(self))),
        )

    @staticmethod
    def unpack(packed: bytes):
        """
        Deserializes the exception
        """
        (class_name, err_msg) = msgpack.unpackb(packed)
        match class_name:
            case SignatureVerificationFailed.__name__:
                return SignatureVerificationFailed(err_msg)
            case DecryptionFailed.__name__:
                return DecryptionFailed(err_msg)
            case UnsupportedMessageType.__name__:
                return UnsupportedMessageType(err_msg)
            case _:
                return SecureMessageHandlerError(err_msg)


class SignatureVerificationFailed(SecureMessageHandlerError):
    """
    Message signature verification failed
    """


class DecryptionFailed(SecureMessageHandlerError):
    """
    Message failed to be decrypted
    """


class UnsupportedMessageType(SecureMessageHandlerError):
    """
    Message with unsupported message type was received
    """


@dataclass(slots=True)
class MessageContext:
    """
    Message context for message handling
    """

    private_key: AlgoPrivateKey
    websocket: Websocket
    sender_encryption_address: EncryptionAddress
    sender_signing_address: SigningAddress
    msg: Message


MessageHandler = Callable[[MessageContext], Awaitable[None]]

MessageHandlers = Tuple[Tuple[Tuple[ULID, ...], MessageHandler], ...]


class SecureMessageHandler(ABC):
    """
    :type:`SecureMessage` message handler
    """

    def __init__(self, private_key: AlgoPrivateKey, message_handlers: MessageHandlers):
        """
        Notes
        -----
        - A MessageHandler may be mapped to 1 or more message types. However, the registered message types must
          be unique across all message handlers, i.e., the relationship is between MessageHandler and Message type
          is 1:N.

        :param private_key: used to verify and decrypt messages
        :param message_handlers: at least 1 message handler mapping needs to be defined.
        """

        if len(message_handlers) == 0:
            raise ValueError("at least 1 MessageHandler must be defined")

        self.__validate_message_handlers(message_handlers)

        self.__private_key = private_key
        self.__message_handlers = message_handlers

    def __validate_message_handlers(self, message_handlers: MessageHandlers):
        """
        Message type IDs across all handlers must be unique
        """
        ids: set[UUID] = set()
        for msg_types, _handler in message_handlers:
            for msg_type in msg_types:
                msg_type_uuid = msg_type.to_uuid()
                if msg_type_uuid in ids:
                    raise ValueError(
                        f"Message type IDs must be unique. Found duplicate: {msg_type}"
                    )
                ids.add(msg_type_uuid)

    async def __call__(self, secure_msg: SecureMessage, websocket: Websocket):
        """
        message handler
        """

        msg = unpack_secure_message(self.__private_key, secure_msg)
        ctx = MessageContext(
            private_key=self.__private_key,
            websocket=websocket,
            sender_encryption_address=secure_msg.secret_msg.sender,
            sender_signing_address=secure_msg.sender,
            msg=msg,
        )

        handler = self.get_handler(msg.type)
        await handler(ctx)

    def get_handler(self, msg_type: ULID) -> MessageHandler:
        """
        Looks up handler for the specified message type.

        If there is no handler registered for the message type, then an error handler is returned.
        """
        for msg_types, handler in self.__message_handlers:
            if msg_type in msg_types:
                return handler

        return self.handle_unsupported_message

    @staticmethod
    async def handle_unsupported_message(ctx: MessageContext):
        """
        Message error handler for unsupported message types.
        """
        def pack_response() -> bytes:
            return pack_secure_message(
                sender_private_key=ctx.private_key,
                msg=UnsupportedMessageType(ctx.msg.type).pack(),
                recipient=ctx.sender_encryption_address,
            ).pack()

        response = await asyncio.to_thread(pack_response)
        await ctx.websocket.send(response)


def pack_secure_message(
        sender_private_key: AlgoPrivateKey,
        msg: Message,
        recipient: EncryptionAddress,
) -> SecureMessage:
    """
    Encrypts and signs the message to construct a SecureMessage
    """
    secret_msg = SecretMessage.encrypt(
        sender_private_key=sender_private_key,
        msg=msg.pack(),
        recipient=recipient,
    )
    return SecureMessage.sign(sender_private_key, secret_msg)


def unpack_secure_message(
        recipient_private_key: AlgoPrivateKey,
        secure_msg: SecureMessage,
) -> Message:
    """
    Verifies the message signature and decrypts the message.
    """
    if not secure_msg.verify():
        raise SignatureVerificationFailed()

    try:
        msg_bytes = secure_msg.secret_msg.decrypt(recipient_private_key)
    except CryptoError as err:
        raise DecryptionFailed() from err

    return Message.unpack(msg_bytes)
