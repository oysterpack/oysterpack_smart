"""
SignTransactionsRequest message handler
"""
import asyncio

from oysterpack.algorand.client.model import AppId, Address
from oysterpack.algorand.client.transactions import payment
from oysterpack.algorand.messaging.secure_message_handler import MessageContext
from oysterpack.apps.multisig_wallet_connect.messsages.sign_transactions import (
    SignTransactionsRequest,
    SignTransactionsFailure,
    ErrCode,
)
from oysterpack.apps.multisig_wallet_connect.protocols.algorand_service import (
    AlgorandService,
)
from oysterpack.apps.multisig_wallet_connect.protocols.multisig_service import (
    MultisigService,
)


class SignTransactionsHandler:
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
        algorand_service: AlgorandService,
    ):
        self.__multisig_service = multisig_service
        self.__algorand_service = algorand_service

    async def __call__(self, ctx: MessageContext):
        try:
            request = await self.__validate_request(ctx)
            await self.__add_service_fee_payment_txn(ctx, request)
        except SignTransactionsFailure as err:
            response = await ctx.pack_secure_message(
                ctx.msg_id, err  # correlate back to request message
            )
            await ctx.websocket.send(response)

    async def __validate_request(self, ctx: MessageContext) -> SignTransactionsRequest:
        """
        Unpacks the message into a SignTransactionsRequest and validate the request.
        """

        def unpack_request() -> SignTransactionsRequest:
            # check message type
            if ctx.msg_type != SignTransactionsRequest.message_type():
                raise SignTransactionsFailure(
                    code=ErrCode.InvalidMessage,
                    message=f"invalid message type: {ctx.msg_type}",
                )
            return SignTransactionsRequest.unpack(ctx.msg_data)

        def check_app_registration(app_id: AppId):
            """
            Check that the app is registered with the service
            """
            raise NotImplementedError

        def check_signer_opted_in(app_id: AppId, account: Address):
            """ "
            Check that the signer is opted into the app
            """
            raise NotImplementedError

        request = unpack_request()
        check_app_registration(request.app_id)
        check_signer_opted_in(request.app_id, request.signer)

        return request

    async def __add_service_fee_payment_txn(
        self,
        ctx: MessageContext,
        request: SignTransactionsRequest,
    ):
        """
        1. Add service fee payment transaction to the request
        2. Assert that the request signer account is able to pay for service and transaction fees
        """

        # add service fee payment transaction
        async with asyncio.TaskGroup() as tg:
            service_fee_task = tg.create_task(self.__multisig_service.service_fee())
            suggested_params_task = tg.create_task(
                self.__algorand_service.suggested_params_with_flat_flee()
            )
            available_algo_balance_task = tg.create_task(
                self.__algorand_service.get_algo_available_balance(request.signer)
            )
        service_fee = service_fee_task.result()
        suggested_params = suggested_params_task.result()
        available_algo_balance = available_algo_balance_task.result()

        service_fee_payment = payment.transfer_algo(
            sender=request.signer,
            receiver=service_fee.pay_to,
            amount=service_fee.amount,
            suggested_params=suggested_params,
            note=str(ctx.msg_id),
        )
        request.transactions.append(
            (
                service_fee_payment,
                service_fee.description,
            )
        )

        # verify signer account has sufficient ALGO funds to pay for service and transaction fees
        total_txn_fees = sum(txn.fee for txn, _desc in request.transactions)
        min_required_algo_balance = service_fee.amount + total_txn_fees
        if available_algo_balance < min_required_algo_balance:
            raise SignTransactionsFailure(
                code=ErrCode.InsufficientAlgoBalance,
                message=f"available ALGO balance is insufficient to pay for service and transaction fees: {available_algo_balance} < {min_required_algo_balance}",
            )
