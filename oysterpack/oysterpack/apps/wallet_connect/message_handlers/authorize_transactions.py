"""
SignTransactionsRequest message handler
"""
import asyncio
import logging
from asyncio import Task, TaskGroup
from typing import Coroutine, Any, TypeVar

from oysterpack.algorand.client.model import TxnId
from oysterpack.algorand.messaging.secure_message_handler import (
    MessageContext,
    MessageHandler,
)
from oysterpack.apps.wallet_connect.messsages.authorize_transactions import (
    AuthorizeTransactionsRequest,
    AuthorizeTransactionsFailure,
    AuthorizeTransactionsErrCode,
    AuthorizeTransactionsRequestAccepted,
    AuthorizeTransactionsError,
    AuthorizeTransactionsSuccess,
)
from oysterpack.apps.wallet_connect.protocols.wallet_connect_service import (
    WalletConnectService,
)
from oysterpack.core.message import MessageType

_T = TypeVar("_T")


class AuthorizeTransactionsHandler(MessageHandler):
    """
    Routes transactions from apps to user accounts for signing.

    Message Structures
    ------------------
    SignedEncryptedMessage
        EncryptedMessage
            Message
                AuthorizeTransactionsRequest

    SignedEncryptedMessage
        EncryptedMessage
            Message
                AuthorizeTransactionsRequestAccepted

    SignedEncryptedMessage
        EncryptedMessage
            Message
                AuthorizeTransactionsSuccess

    SignedEncryptedMessage
        EncryptedMessage
            Message
                AuthorizeTransactionsFailure


    Notes
    -----
    - All user accounts are rekeyed to multisig accounts.
    """

    def __init__(
        self,
        wallet_connect: WalletConnectService,
    ):
        self.__wallet_connect = wallet_connect

        self.__tasks: set[Task] = set()
        self.__logger = logging.getLogger(__name__)

    def supported_msg_types(self) -> set[MessageType]:
        return {AuthorizeTransactionsRequest.message_type()}

    async def __call__(self, ctx: MessageContext):
        try:
            request = await self.__unpack_request(ctx)
            try:
                async with TaskGroup() as tg:
                    tg.create_task(self.__check_app_keys(ctx, request))
                    tg.create_task(self.__check_authorizer_subscription(request))
                    tg.create_task(self.__check_wallet_app_connection(request))
                    tg.create_task(self.__validate_transactions(request))
            except ExceptionGroup as err:
                raise err.exceptions[0]
            await self._request_accepted(ctx)
            await self.__authorize_transactions(request)
            txnids = await self.__wallet_connect.sign_transactions(request)
            await self._send_success_message(ctx, txnids)
        except AuthorizeTransactionsError as err:
            self._create_task(
                self._handle_failure(ctx, err.to_failure()), "handle_failure"
            )
        except Exception as err:
            failure = AuthorizeTransactionsFailure(
                code=AuthorizeTransactionsErrCode.Failure,
                message=f"server error: {err}",
            )
            self._create_task(self._handle_failure(ctx, failure), "handle_failure")

    def __task_done(self, task: Task):
        self.__tasks.remove(task)
        name = task.get_name()
        self.__logger.debug("task done [%s]", name)
        if task.exception() is not None:
            self.__logger.error("task failed [%s] %s", name, task.exception())

    def _create_task(self, coro: Coroutine[Any, Any, _T], name: str) -> Task[_T]:
        task = asyncio.create_task(coro, name=name)
        self.__tasks.add(task)
        task.add_done_callback(self.__task_done)
        return task

    async def _request_accepted(self, ctx: MessageContext):
        """
        Send back an acknowledgement that the request has been accepted.
        """
        msg = await ctx.pack_secure_message(
            ctx.msg_id,  # correlate back to request message
            AuthorizeTransactionsRequestAccepted(),
        )
        await ctx.websocket.send(msg)

    async def _handle_failure(
        self,
        ctx: MessageContext,
        err: AuthorizeTransactionsFailure,
    ):
        self.__logger.error(err)
        msg = await ctx.pack_secure_message(
            ctx.msg_id,  # correlate back to request message
            err,
        )
        await ctx.websocket.send(msg)

    async def _send_success_message(
        self,
        ctx: MessageContext,
        txnids: list[TxnId],
    ):
        msg = await ctx.pack_secure_message(
            ctx.msg_id,  # correlate back to request message
            AuthorizeTransactionsSuccess(txnids),
        )
        await ctx.websocket.send(msg)

    async def __unpack_request(
        self, ctx: MessageContext
    ) -> AuthorizeTransactionsRequest:
        # check message type
        if ctx.msg_type != AuthorizeTransactionsRequest.message_type():
            raise AuthorizeTransactionsError(
                code=AuthorizeTransactionsErrCode.InvalidMessage,
                message=f"invalid message type: {ctx.msg_type}",
            )

        return await asyncio.get_event_loop().run_in_executor(
            ctx.executor, AuthorizeTransactionsRequest.unpack, ctx.msg_data
        )

    async def __check_app_keys(
        self,
        ctx: MessageContext,
        request: AuthorizeTransactionsRequest,
    ):
        app_id = request.app_id
        signing_address = ctx.client_signing_address
        encryption_address = ctx.client_encryption_address
        app = await self.__wallet_connect.app(app_id)
        if app is None:
            raise AuthorizeTransactionsError(
                code=AuthorizeTransactionsErrCode.AppNotRegistered,
                message="app is not registered",
            )
        if not app.enabled:
            raise AuthorizeTransactionsError(
                code=AuthorizeTransactionsErrCode.AppDisabled,
                message="app is disabled",
            )

        if not await self.__wallet_connect.app_keys_registered(
            app_id=app_id,
            signing_address=signing_address,
            encryption_address=encryption_address,
        ):
            raise AuthorizeTransactionsError(
                code=AuthorizeTransactionsErrCode.UnauthorizedMessage,
                message="keys used to sign and encrypt the message are not registered with the app",
            )

    async def __check_authorizer_subscription(
        self, request: AuthorizeTransactionsRequest
    ):
        subscription = await self.__wallet_connect.account_subscription(
            request.authorizer
        )
        if subscription is None:
            raise AuthorizeTransactionsError(
                code=AuthorizeTransactionsErrCode.AccountNotRegistered,
                message="account is not registered",
            )

        if subscription.expired:
            raise AuthorizeTransactionsError(
                code=AuthorizeTransactionsErrCode.AccountSubscriptionExpired,
                message="account subscription is expired",
            )

    async def __check_wallet_app_connection(
        self,
        request: AuthorizeTransactionsRequest,
    ):
        keys = await self.__wallet_connect.wallet_app_conn_public_keys(
            account=request.authorizer,
            app_id=request.app_id,
        )
        if keys is None:
            raise AuthorizeTransactionsError(
                code=AuthorizeTransactionsErrCode.WalletConnectAppDisconnected,
                message="wallet is not connected to the app",
            )

    async def __validate_transactions(
        self,
        request: AuthorizeTransactionsRequest,
    ):
        app_activity_spec = self.__wallet_connect.app_activity_spec(
            request.app_activity_id
        )
        if app_activity_spec is None:
            raise AuthorizeTransactionsError(
                code=AuthorizeTransactionsErrCode.InvalidAppActivityId,
                message="invalid app activity ID",
            )
        if not await self.__wallet_connect.app_activity_registered(
            app_id=request.app_id,
            app_activity_id=request.app_activity_id,
        ):
            raise AuthorizeTransactionsError(
                code=AuthorizeTransactionsErrCode.AppActivityNotRegistered,
                message="activity is not registered for the app",
            )

        try:
            # validate individual transactions
            async with TaskGroup() as tg:
                for (txn, activity_id) in request.transactions:
                    txn_activity_spec = self.__wallet_connect.txn_activity_spec(
                        activity_id
                    )
                    if txn_activity_spec is None:
                        raise AuthorizeTransactionsError(
                            code=AuthorizeTransactionsErrCode.InvalidTxnActivityId,
                            message=f"invalid transaction activity ID: {activity_id}",
                        )
                    tg.create_task(txn_activity_spec.validate(txn))
        except ExceptionGroup as err:
            self.__logger.error(f"invalid transaction: {err}")
            exception = err.exceptions[0]
            if isinstance(exception, AuthorizeTransactionsError):
                raise exception
            raise AuthorizeTransactionsError(
                code=AuthorizeTransactionsErrCode.InvalidTxnActivity,
                message=str(exception),
            )

        try:
            await app_activity_spec.validate(request.transactions)
        except Exception as err:
            raise AuthorizeTransactionsError(
                code=AuthorizeTransactionsErrCode.InvalidAppActivity,
                message=f"invalid app activity: {request.app_activity_id} : {err}",
            )

    async def __authorize_transactions(self, request: AuthorizeTransactionsRequest):
        approved = await self.__wallet_connect.authorize_transactions(request)

        if not approved:
            raise AuthorizeTransactionsError(
                code=AuthorizeTransactionsErrCode.Rejected,
                message="authorizer rejected the transactions",
            )
