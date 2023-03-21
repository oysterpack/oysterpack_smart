"""
SecureMessage handler
"""
import asyncio
from asyncio import Task
from concurrent.futures import Executor
from dataclasses import dataclass
from datetime import datetime, UTC
from enum import IntEnum, auto
from typing import Final, Callable, Awaitable, Self, Tuple

import msgpack  # type: ignore
from nacl.exceptions import CryptoError
from ulid import ULID
from websockets.legacy.server import WebSocketServerProtocol

from oysterpack.algorand.client.accounts.private_key import (
    AlgoPrivateKey,
    EncryptionAddress,
    SigningAddress,
)
from oysterpack.algorand.messaging.secure_message import (
    SignedEncryptedMessage,
    pack_secure_message,
)
from oysterpack.algorand.messaging.websocket import Websocket
from oysterpack.core.logging import get_logger
from oysterpack.core.message import (
    Message,
    MessageId,
    MessageType,
    MultisigMessage,
    SignedMessage,
    Serializable,
)


class SecureMessageHandlerErrorCode(IntEnum):
    SIGNATURE_VERIFICATION_FAILED = auto()
    DECRYPTION_FAILED = auto()
    # Message with unsupported message type was received
    UNSUPPORTED_MSG_TYPE = auto()
    INVALID_MSG = auto()


class SecureMessageHandlerError(Exception, Serializable):
    """
    SecureMessageHandler base exception
    """

    MSG_TYPE: Final[MessageType] = MessageType.from_str("01GVGS7ZK6WE9C3TDRBTVVAJ3J")

    def __init__(self, err_code: SecureMessageHandlerErrorCode, msg: str):
        self.err_code = err_code
        self.msg = msg

    @classmethod
    def message_type(cls) -> MessageType:
        return cls.MSG_TYPE

    def to_message(self) -> Message:
        return Message(
            msg_id=MessageId(),
            msg_type=self.MSG_TYPE,
            data=self.pack(),
        )

    def pack(self) -> bytes:
        """
        Serializes the exception into a Message
        """
        return msgpack.packb(
            (
                self.err_code,
                self.msg,
            )
        )

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        """
        Deserializes the exception
        """
        err_code, err_msg = msgpack.unpackb(packed)
        return cls(err_code, err_msg)


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
    # used to run non-blocking code that is CPU intensive
    executor: Executor

    # who sent the message
    client_encryption_address: EncryptionAddress
    # who signed the message
    client_signing_address: SigningAddress
    # decrypted message
    msg: Message
    # If not None, then the msg data was a signed message, which is the actual message to process
    signed_msg_data: SignedMessage | MultisigMessage | None = None

    async def pack_secure_message(
        self,
        data: Serializable,
        recipient: EncryptionAddress | None = None,
    ) -> bytes:
        """
        Wraps the `msg` into a :type:`SecureMessage` and serializes it to bytes

        :param msg: provides the message to be wrapped in a :type:`SecureMessage`
        :param recipient: if None, then the client is used as the recipient
        :return: serialized :type:`SecureMessage` bytes
        """

        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            pack_secure_message,
            self.server_private_key,
            data,
            recipient if recipient else self.client_encryption_address,
        )

    @property
    def msg_type(self) -> MessageType:
        """
        :return: msg type
        """
        if self.signed_msg_data is not None:
            return self.signed_msg_data.msg_type

        return self.msg.msg_type

    @property
    def msg_data(self) -> bytes:
        """
        :return: serialized msg data
        """
        if self.signed_msg_data is not None:
            return self.signed_msg_data.data

        return self.msg.data


# async message handler
MessageHandler = Callable[[MessageContext], Awaitable[None]]


@dataclass(slots=True)
class MessageHandlerMapping:
    msg_handler: MessageHandler
    msg_types: set[MessageType]


# MessagHandler:MessageType is a 1:N relationship
MessageHandlers = Tuple[MessageHandlerMapping, ...]

# TODO: add logging
class SecureMessageHandler:
    """
    Callable[[SecureMessage],Websocket]

    Routes :type:`SecureMessage` to registered :type:`MessageHandler`

    :type:`SecureMessage` handler, where the encrypted messages are of :type:`Message`
    """

    def __init__(
        self,
        private_key: AlgoPrivateKey,
        message_handlers: MessageHandlers,
        executor: Executor,
    ):
        """
        Notes
        -----
        - A MessageHandler may be mapped to 1 or more message types. However, the registered message types must
          be unique across all message handlers, i.e., the relationship is between MessageHandler and Message type
          is 1:N.

        :param private_key: used to verify and decrypt messages
        :param message_handlers: at least 1 message handler mapping needs to be defined.
        :param executor: executor used for non-blocking code
        """

        if len(message_handlers) == 0:
            raise ValueError("at least 1 MessageHandler must be defined")

        self.__validate_message_handlers(message_handlers)

        self.__private_key = private_key
        self.__message_handlers = message_handlers
        self.__executor = executor

    def __validate_message_handlers(self, message_handlers: MessageHandlers):
        """
        Message type IDs across all handlers must be unique
        """
        ids: set[ULID] = set()
        for mapping in message_handlers:
            for msg_type in mapping.msg_types:
                if msg_type in ids:
                    raise ValueError(
                        f"Message type IDs must be unique. Found duplicate: {msg_type}"
                    )
                ids.add(msg_type)

    async def __call__(self, secure_msg: SignedEncryptedMessage, websocket: Websocket):
        """
        Workflow
        --------
        1. verify the message signature
        2. decrypt the message
        3. lookup message handler
        4. handle message
        """
        msg: Message | SignedMessage | MultisigMessage
        try:
            msg = unpack_secure_message(self.__private_key, secure_msg)
        except SecureMessageHandlerError as err:
            await self._handle_secure_message_handler_error(
                err=err,
                secure_msg=secure_msg,
                websocket=websocket,
            )
            return

        ctx = MessageContext(
            server_private_key=self.__private_key,
            websocket=websocket,
            client_encryption_address=secure_msg.encrypted_msg.sender,
            client_signing_address=secure_msg.sender,
            msg=msg,
            executor=self.__executor,
        )

        if msg.msg_type == SignedMessage.message_type():
            ctx.signed_msg_data = SignedMessage.unpack(msg.data)
            if not ctx.signed_msg_data.verify():
                await self._handle_secure_message_handler_error(
                    err=SecureMessageHandlerError(
                        SecureMessageHandlerErrorCode.SIGNATURE_VERIFICATION_FAILED,
                        "message data signature verification failed",
                    ),
                    secure_msg=secure_msg,
                    websocket=websocket,
                )
                return
            handler = self.get_handler(ctx.signed_msg_data.msg_type)
        elif msg.msg_type == MultisigMessage.message_type():
            ctx.signed_msg_data = MultisigMessage.unpack(msg.data)
            if not ctx.signed_msg_data.verify():
                await self._handle_secure_message_handler_error(
                    err=SecureMessageHandlerError(
                        SecureMessageHandlerErrorCode.SIGNATURE_VERIFICATION_FAILED,
                        "message data multisig verification failed",
                    ),
                    secure_msg=secure_msg,
                    websocket=websocket,
                )
                return
            handler = self.get_handler(ctx.signed_msg_data.msg_type)
        else:
            handler = self.get_handler(msg.msg_type)

        await handler(ctx)

    async def _handle_secure_message_handler_error(
        self,
        err: SecureMessageHandlerError,
        secure_msg: SignedEncryptedMessage,
        websocket: Websocket,
    ):
        secure_message = await asyncio.get_event_loop().run_in_executor(
            self.__executor,
            pack_secure_message,
            self.__private_key,
            err,
            secure_msg.encrypted_msg.sender,
        )
        await websocket.send(secure_message)

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
            response = await ctx.pack_secure_message(
                SecureMessageHandlerError(
                    SecureMessageHandlerErrorCode.UNSUPPORTED_MSG_TYPE,
                    str(ctx.msg.msg_type),
                )
            )
            await ctx.websocket.send(response)

        for mapping in self.__message_handlers:
            if msg_type in mapping.msg_types:
                return mapping.msg_handler

        return handle_unsupported_message


@dataclass(slots=True)
class SecureMessageWebsocketHandlerMetrics:
    total_msgs_received: int = 0

    success_count: int = 0
    failure_count: int = 0

    last_msg_recv_timestamp: datetime = datetime.fromtimestamp(0, UTC)
    last_msg_success_timestamp: datetime = datetime.fromtimestamp(0, UTC)
    last_msg_failure_timestamp: datetime = datetime.fromtimestamp(0, UTC)


class SecureMessageWebsocketHandler:
    """
    :type:`WebsocketHandler` for :type:`SecureMessage`

    Notes
    -----
    - Any exception that is raised while processing a message will result in the websocket connection to be closed.
    """

    def __init__(
        self,
        handler: SecureMessageHandler,
        max_concurrent_requests: int = 1000,
    ):
        """
        :param handler: SecureMessageHandler
        :param max_concurrent_requests: used to limit the number of requests that are processed concurrently.
            When the max limit is reached, then requests will be throttled.
        """
        self.__handler = handler
        self.__max_concurrent_requests = max_concurrent_requests
        self.__tasks: set[Task] = set()

        self.__metrics = SecureMessageWebsocketHandlerMetrics()
        self.__logger = get_logger(self)

    async def __call__(self, websocket: WebSocketServerProtocol):
        def log_msg_recv():
            self.__metrics.total_msgs_received += 1
            self.__metrics.last_msg_recv_timestamp = datetime.now(UTC)
            self.__logger.debug("message received")

        def log_msg_success():
            self.__metrics.success_count += 1
            self.__metrics.last_msg_success_timestamp = datetime.now(UTC)
            self.__logger.debug("message handled")

        def log_msg_failure(err: BaseException):
            self.__metrics.failure_count += 1
            self.__metrics.last_msg_failure_timestamp = datetime.now(UTC)
            self.__logger.exception("message failure: %s", err)

        async for msg in websocket:
            if isinstance(msg, bytes):
                log_msg_recv()

                try:
                    secure_msg = SignedEncryptedMessage.unpack(msg)
                except BaseException as err:
                    log_msg_failure(err)
                    raise

                if self.request_task_count < self.__max_concurrent_requests:
                    # process task concurrently
                    task = asyncio.create_task(self.__handler(secure_msg, websocket))
                    self.__tasks.add(task)

                    def on_done(task: Task):
                        self.__tasks.remove(task)
                        task_err = task.exception()
                        if task_err is None:
                            log_msg_success()
                        else:
                            log_msg_failure(task_err)

                    task.add_done_callback(on_done)
                else:
                    # throttle
                    try:
                        await self.__handler(secure_msg, websocket)
                        log_msg_success()
                    except BaseException as err:
                        log_msg_failure(err)
                        raise
            else:
                invalid_msg_err = SecureMessageHandlerError(
                    SecureMessageHandlerErrorCode.INVALID_MSG,
                    "message must be a SecureMessage serialzed bytes message using MessagePack",
                )
                log_msg_failure(invalid_msg_err)

    @property
    def max_concurrent_requests(self) -> int:
        return self.__max_concurrent_requests

    @property
    def request_task_count(self) -> int:
        return len(self.__tasks)

    @property
    def metrics(self) -> SecureMessageWebsocketHandlerMetrics:
        """
        :return: SecureMessageWebsocketHandlerMetrics
        """
        return self.__metrics


def unpack_secure_message(
    recipient_private_key: AlgoPrivateKey,
    secure_msg: SignedEncryptedMessage,
) -> Message:
    """
    Verifies the message signature and decrypts the message.
    """
    if not secure_msg.verify():
        raise SecureMessageHandlerError(
            SecureMessageHandlerErrorCode.SIGNATURE_VERIFICATION_FAILED,
            "signature verification failed",
        )

    try:
        msg_bytes = secure_msg.encrypted_msg.decrypt(recipient_private_key)
    except CryptoError as err:
        raise SecureMessageHandlerError(
            SecureMessageHandlerErrorCode.DECRYPTION_FAILED,
            "decryption failed",
        ) from err

    try:
        return Message.unpack(msg_bytes)
    except Exception as err:
        raise SecureMessageHandlerError(
            SecureMessageHandlerErrorCode.INVALID_MSG,
            f"failed to unpack message: {err}",
        ) from err
