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

from oysterpack.algorand.client.accounts.private_key import (
    AlgoPrivateKey,
    EncryptionAddress,
    SigningAddress,
)
from oysterpack.algorand.messaging.secure_message import SecureMessage, SecretMessage
from oysterpack.algorand.messaging.websocket import Websocket
from oysterpack.core.message import Message, MessageId, MessageType


class SecureMessageHandlerError(Exception):
    """
    SecureMessageHandler base exception
    """

    MSG_TYPE: Final[MessageType] = MessageType.from_str("01GVGS7ZK6WE9C3TDRBTVVAJ3J")

    def pack(self, msg_id: MessageId | None = None) -> Message:
        """
        Serializes the exception into a Message
        """
        return Message(
            id=msg_id if msg_id else MessageId(),
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

    # used to secure the message transport
    # all messages sent between the client and server are box encrypted and signed
    server_private_key: AlgoPrivateKey

    # used to communicate with the client
    websocket: Websocket

    # who sent the message
    client_encryption_address: EncryptionAddress
    # who signed the message
    client_signing_address: SigningAddress
    # decrypted message
    msg: Message

    async def pack_secure_message_bytes(
        self,
        msg: Callable[[], Message],
        recipient: EncryptionAddress | None = None,
    ) -> bytes:
        """
        Packs the message into a :type:`SecureMessage` and serializes it to bytes

        :param msg: provides the message
        :param recipient: if None, then the client is used as the recipient
        :return: serialized :type:`SecureMessage` bytes
        """

        def pack_response() -> bytes:
            return pack_secure_message(
                sender_private_key=self.server_private_key,
                msg=msg(),
                recipient=recipient if recipient else self.client_encryption_address,
            ).pack()

        return await asyncio.to_thread(pack_response)


MessageHandler = Callable[[MessageContext], Awaitable[None]]

# MessagHandler:MessageType is a 1:N relationship
MessageHandlers = Tuple[Tuple[MessageHandler, Tuple[MessageType, ...]], ...]


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
        for _handler, msg_types in message_handlers:
            for msg_type in msg_types:
                msg_type_uuid = msg_type.to_uuid()
                if msg_type_uuid in ids:
                    raise ValueError(
                        f"Message type IDs must be unique. Found duplicate: {msg_type}"
                    )
                ids.add(msg_type_uuid)

    async def __call__(self, secure_msg: SecureMessage, websocket: Websocket):
        """
        Workflow
        --------
        1. verify the message signature
        2. decrypt the message
        3. lookup message handler
        4. handle message
        """
        try:
            msg = unpack_secure_message(self.__private_key, secure_msg)
        except SecureMessageHandlerError as err:
            msg = err.pack()

        ctx = MessageContext(
            server_private_key=self.__private_key,
            websocket=websocket,
            client_encryption_address=secure_msg.secret_msg.sender,
            client_signing_address=secure_msg.sender,
            msg=msg,
        )

        handler = self.get_handler(msg.type)
        await handler(ctx)

    def get_handler(self, msg_type: MessageType) -> MessageHandler:
        """
        Looks up handler for the specified message type.

        Notes
        -----
        - The following scenarios are handled
          - When there is no handler registered for the message type
          - SecureMessageHandlerError
        """

        async def handle_unsupported_message(ctx: MessageContext):
            response = await ctx.pack_secure_message_bytes(
                UnsupportedMessageType(ctx.msg.type).pack
            )
            await ctx.websocket.send(response)

        for handler, msg_types in self.__message_handlers:
            if msg_type in msg_types:
                return handler

        async def handle_error(ctx: MessageContext):
            response = await ctx.pack_secure_message_bytes(lambda: ctx.msg)
            await ctx.websocket.send(response)

        if msg_type == SecureMessageHandlerError.MSG_TYPE:
            return handle_error

        return handle_unsupported_message


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
