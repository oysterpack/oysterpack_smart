"""
SignTransactionsRequest message handler
"""
import asyncio
import logging
from asyncio import Task, TaskGroup
from typing import Coroutine, Any, TypeVar

from oysterpack.algorand.client.model import AppId, Address
from oysterpack.algorand.messaging.secure_message_handler import (
    MessageContext,
    MessageHandler,
)
from oysterpack.apps.multisig_wallet_connect.messsages.sign_transactions import (
    SignTransactionsRequest,
    SignTransactionsFailure,
    ErrCode,
    SignTransactionsRequestAccepted,
    SignTransactionsError,
)
from oysterpack.apps.multisig_wallet_connect.protocols.multisig_service import (
    MultisigService,
)
from oysterpack.core.message import MessageType

_T = TypeVar("_T")


class SignTransactionsHandler(MessageHandler):
    """
    Routes transactions from apps to user accounts for signing.

    Message Structures
    ------------------
    SignedEncryptedMessage
        EncryptedMessage
            Message
                SignTransactionsRequest

    SignedEncryptedMessage
        EncryptedMessage
            Message
                SignTransactionsRequestAccepted

    SignedEncryptedMessage
        EncryptedMessage
            Message
                SignTransactionsSuccess

    SignedEncryptedMessage
        EncryptedMessage
            Message
                SignTransactionsFailure

    SignedEncryptedMessage
        EncryptedMessage
            Message
                SignMultisigTransactionsMessage


    Notes
    -----
    - All user accounts are rekeyed to multisig accounts.
    """

    def __init__(
            self,
            multisig_service: MultisigService,
    ):
        self.__multisig_service = multisig_service

        self.__tasks: set[Task] = set()
        self.__logger = logging.getLogger(__name__)

    def supported_msg_types(self) -> set[MessageType]:
        return {SignTransactionsRequest.message_type()}

    async def __call__(self, ctx: MessageContext):
        try:
            request = await self.__unpack_request(ctx)
            await self.__validate_request(request)
            self._create_task(self._request_accepted(ctx), "request_accepted")
            await self.__get_signer_authorization(request)
        except SignTransactionsError as err:
            self._create_task(
                self._handle_failure(ctx, err.to_failure()), "handle_failure"
            )

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
            SignTransactionsRequestAccepted(),
        )
        await ctx.websocket.send(msg)

    async def _handle_failure(self, ctx: MessageContext, err: SignTransactionsFailure):
        self.__logger.error(err)
        msg = await ctx.pack_secure_message(
            ctx.msg_id,  # correlate back to request message
            err,
        )
        await ctx.websocket.send(msg)

    async def __unpack_request(self, ctx: MessageContext) -> SignTransactionsRequest:
        # check message type
        if ctx.msg_type != SignTransactionsRequest.message_type():
            raise SignTransactionsError(
                code=ErrCode.InvalidMessage,
                message=f"invalid message type: {ctx.msg_type}",
            )

        return await asyncio.get_event_loop().run_in_executor(
            ctx.executor, SignTransactionsRequest.unpack, ctx.msg_data
        )

    async def __validate_request(
            self, request: SignTransactionsRequest
    ) -> SignTransactionsRequest:
        async def check_app_registration(app_id: AppId):
            """
            Check that the app is registered with the service
            """
            if not await self.__multisig_service.is_app_registered(app_id):
                raise SignTransactionsError(
                    code=ErrCode.AppNotRegistered,
                    message="app is not registered",
                )

        async def check_signer_registration(account: Address, app_id: AppId):
            """ "
            Check that the signer is opted into the multisig service and the app
            """
            if not await self.__multisig_service.is_account_registered(
                    account=account,
                    app_id=app_id,
            ):
                raise SignTransactionsError(
                    code=ErrCode.SignerNotRegistered,
                    message="signer is not registered",
                )

        async def check_signer_subscription(account: Address):
            subscription = await self.__multisig_service.get_account_subscription(account)
            if subscription is None:
                raise SignTransactionsError(
                    code=ErrCode.SignerNotSubscribed,
                    message="signer has no subscription",
                )

            if subscription.expired:
                raise SignTransactionsError(
                    code=ErrCode.SignerSubscriptionExpired,
                    message="signer subscription is expired",
                )

        async def check_activity(request: SignTransactionsRequest) -> None:
            app_activity_spec = self.__multisig_service.get_app_activity_spec(
                request.app_activity_id
            )
            if app_activity_spec is None:
                raise SignTransactionsError(
                    code=ErrCode.InvalidAppActivityId,
                    message="invalid app activity ID",
                )
            if not await self.__multisig_service.is_app_activity_registered(
                    app_id=request.app_id,
                    app_activity_id=request.app_activity_id,
            ):
                raise SignTransactionsError(
                    code=ErrCode.AppActivityNotRegistered,
                    message="activity is not registered for the app",
                )

            try:
                # validate individual transactions
                async with TaskGroup() as tg:
                    for (txn, activity_id) in request.transactions:
                        txn_activity_spec = self.__multisig_service.get_txn_activity_spec(
                            activity_id
                        )
                        if txn_activity_spec is None:
                            raise SignTransactionsError(
                                code=ErrCode.InvalidTxnActivityId,
                                message=f"invalid transaction activity ID: {activity_id}",
                            )
                        tg.create_task(txn_activity_spec.validate(txn))
            except ExceptionGroup as err:
                self.__logger.error(f"invalid transaction: {err}")
                exception = err.exceptions[0]
                if isinstance(exception, SignTransactionsError):
                    raise exception
                raise SignTransactionsError(
                    code=ErrCode.InvalidTxnActivity,
                    message=str(exception)
                )


            try:
                await app_activity_spec.validate(request.transactions)
            except Exception as err:
                raise SignTransactionsError(
                    code=ErrCode.InvalidAppActivity,
                    message=f"invalid app activity: {request.app_activity_id} : {err}",
                )

        try:
            async with TaskGroup() as tg:
                tg.create_task(check_app_registration(request.app_id))
                tg.create_task(check_signer_registration(
                    account=request.signer,
                    app_id=request.app_id,
                ))
                tg.create_task(check_signer_subscription(account=request.signer))
        except ExceptionGroup as err:
            self.__logger.error(err)
            raise err.exceptions[0]

        await check_activity(request)

        return request

    async def __get_signer_authorization(self, request: SignTransactionsRequest):
        raise NotImplementedError()
