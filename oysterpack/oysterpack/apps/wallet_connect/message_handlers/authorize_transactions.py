"""
SignTransactionsRequest message handler
"""
import asyncio
import logging
from asyncio import Task, TaskGroup
from typing import Coroutine, Any, TypeVar

from oysterpack.algorand.client.model import AppId, Address, TxnId
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
    AppNotRegistered,
    AccountSubscriptionExpired,
    AccountNotRegistered,
    AccountNotOptedIntoApp,
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
            await self.__validate_request(request)
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

    async def __validate_request(
        self, request: AuthorizeTransactionsRequest
    ) -> AuthorizeTransactionsRequest:
        async def check_wallet_app_connection(account: Address, app_id: AppId):
            try:
                if not await self.__wallet_connect.wallet_connected(
                    account=account,
                    app_id=app_id,
                ):
                    raise AuthorizeTransactionsError(
                        code=AuthorizeTransactionsErrCode.WalletConnectAppDisconnected,
                        message="wallet is not currently connected to the app",
                    )
            except AppNotRegistered:
                raise AuthorizeTransactionsError(
                    code=AuthorizeTransactionsErrCode.AppNotRegistered,
                    message="app is not registered",
                )
            except AccountNotRegistered:
                raise AuthorizeTransactionsError(
                    code=AuthorizeTransactionsErrCode.AccountNotRegistered,
                    message="account is not registered",
                )
            except AccountNotOptedIntoApp:
                raise AuthorizeTransactionsError(
                    code=AuthorizeTransactionsErrCode.AccountNotOptedIntoApp,
                    message="account is not opted into the app",
                )
            except AccountSubscriptionExpired:
                raise AuthorizeTransactionsError(
                    code=AuthorizeTransactionsErrCode.AccountSubscriptionExpired,
                    message="account subscription is expired",
                )

        async def check_activity(request: AuthorizeTransactionsRequest) -> None:
            app_activity_spec = self.__wallet_connect.get_app_activity_spec(
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
                        txn_activity_spec = self.__wallet_connect.get_txn_activity_spec(
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

        await check_wallet_app_connection(
            account=request.authorizer,
            app_id=request.app_id,
        )
        await check_activity(request)

        return request

    async def __authorize_transactions(self, request: AuthorizeTransactionsRequest):
        approved = await self.__wallet_connect.authorize_transactions(request)

        if not approved:
            raise AuthorizeTransactionsError(
                code=AuthorizeTransactionsErrCode.Rejected,
                message="authorizer rejected the transactions",
            )
