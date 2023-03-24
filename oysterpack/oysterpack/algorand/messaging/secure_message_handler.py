"""
SecureMessage handler
"""
import asyncio
from asyncio import Task
from concurrent.futures import Executor
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Callable, Awaitable, Tuple, ClassVar

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
    unpack_secure_message,
    InvalidSecureMessage,
)
from oysterpack.algorand.messaging.websocket import Websocket, CloseCode
from oysterpack.core.logging import get_logger
from oysterpack.core.message import (
    Message,
    MessageType,
    Serializable,
    MessageId,
)


class SecureMessageHandlerError(Exception):
    """
    SecureMessageHandler base exception
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
    # used to run non-blocking code that is CPU intensive
    executor: Executor

    # who sent the message
    client_encryption_address: EncryptionAddress
    # who signed the message
    client_signing_address: SigningAddress
    # decrypted message
    msg: Message

    async def pack_secure_message(
        self,
        msg_id: MessageId,
        data: Serializable,
        recipient: EncryptionAddress | None = None,
    ) -> bytes:
        """
        Wraps the `data` into a :type:`SecureMessage` and serializes it to bytes

        :param msg_id: unique message ID
        :param data: provides the message to be wrapped in a :type:`SecureMessage`
        :param recipient: if None, then the client is used as the recipient
        :return: serialized :type:`SecureMessage` bytes
        """

        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            pack_secure_message,
            self.server_private_key,
            data,
            recipient if recipient else self.client_encryption_address,
            msg_id,
        )

    @property
    def msg_id(self) -> MessageId:
        return self.msg.msg_id

    @property
    def msg_type(self) -> MessageType:
        """
        :return: msg type
        """
        return self.msg.msg_type

    @property
    def msg_data(self) -> bytes:
        """
        :return: serialized msg data
        """
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
        self.__logger = get_logger(self)

    @staticmethod
    def __validate_message_handlers(message_handlers: MessageHandlers):
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
        try:
            msg = unpack_secure_message(self.__private_key, secure_msg)
        except InvalidSecureMessage as err:
            await websocket.close(code=CloseCode.GOING_AWAY, reason="invalid message")
            self.__logger.exception(err)
            return

        ctx = MessageContext(
            server_private_key=self.__private_key,
            websocket=websocket,
            client_encryption_address=secure_msg.encrypted_msg.sender,
            client_signing_address=secure_msg.sender,
            msg=msg,
            executor=self.__executor,
        )

        handler = self.get_handler(msg.msg_type)
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
            await ctx.websocket.close(
                code=CloseCode.GOING_AWAY, reason="unsupported msg type"
            )
            self.__logger.error("unsupported message type: %s", ctx.msg.msg_type)

        for mapping in self.__message_handlers:
            if msg_type in mapping.msg_types:
                return mapping.msg_handler

        return handle_unsupported_message


@dataclass(slots=True)
class SecureMessageWebsocketHandlerMetrics:
    total_msgs_received: int = 0

    success_count: int = 0
    failure_count: int = 0
    throttle_count: int = 0

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

    # 1001 indicates the connection was closed (going away)
    MSG_HANDLER_ERR_CODE: ClassVar[int] = 1001

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
            self.__logger.debug("message received: %s", self.__metrics)

        def log_msg_success():
            self.__metrics.success_count += 1
            self.__metrics.last_msg_success_timestamp = datetime.now(UTC)
            self.__logger.debug("message handled: %s", self.__metrics)

        def log_msg_failure(err: BaseException):
            self.__metrics.failure_count += 1
            self.__metrics.last_msg_failure_timestamp = datetime.now(UTC)
            self.__logger.debug("message failure: %s", self.__metrics)

            # exceptions raised by background asyncio have no traceback
            if err.__traceback__:
                self.__logger.exception("message failure: %s", err)
            else:
                self.__logger.error("message failure: %s", err)

        def log_throttled():
            self.__metrics.throttle_count += 1
            self.__logger.warning(
                "requests are being throttled - throttle count = %s",
                self.__metrics.throttle_count,
            )

        async for msg in websocket:
            if isinstance(msg, bytes):
                log_msg_recv()

                try:
                    secure_msg = SignedEncryptedMessage.unpack(msg)
                except BaseException as err:
                    await websocket.close(
                        code=self.MSG_HANDLER_ERR_CODE, reason="invalid message"
                    )
                    err.add_note("SignedEncryptedMessage.unpack(msg) failed")
                    log_msg_failure(err)
                    return

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
                            close_task = asyncio.create_task(
                                websocket.close(
                                    code=self.MSG_HANDLER_ERR_CODE,
                                    reason="message handler failed",
                                )
                            )
                            self.__tasks.add(close_task)
                            close_task.add_done_callback(self.__tasks.remove)
                            log_msg_failure(
                                SecureMessageHandlerError(
                                    f"{type(task_err)} : {task_err}"
                                )
                            )

                    task.add_done_callback(on_done)
                else:
                    # throttle
                    log_throttled()
                    try:
                        await self.__handler(secure_msg, websocket)
                        log_msg_success()
                    except BaseException as err:
                        await websocket.close(
                            code=self.MSG_HANDLER_ERR_CODE,
                            reason="message handler failed",
                        )
                        err.add_note("message handler task failed")
                        log_msg_failure(err)
                        return
            else:
                await websocket.close(
                    code=self.MSG_HANDLER_ERR_CODE, reason="invalid message"
                )
                log_msg_failure(
                    SecureMessageHandlerError(f"unsupported msg type: {type(msg)}")
                )
                return

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
