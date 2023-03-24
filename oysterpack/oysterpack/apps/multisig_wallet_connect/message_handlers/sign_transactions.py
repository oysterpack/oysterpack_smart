"""
SignTransactionsRequest message handler
"""
from algosdk.transaction import PaymentTxn

from oysterpack.algorand.client.model import AppId, Address
from oysterpack.algorand.messaging.secure_message_handler import MessageContext
from oysterpack.apps.multisig_wallet_connect.messsages.sign_transactions import (
    SignTransactionsRequest,
    SignTransactionsFailure,
    ErrCode,
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

    async def __call__(self, ctx: MessageContext):
        try:
            request = self.__validate_request(ctx)
        except SignTransactionsFailure as err:
            response = await ctx.pack_secure_message(
                ctx.msg_id, err  # correlate back to request message
            )
            await ctx.websocket.send(response)

    def __validate_request(self, ctx: MessageContext) -> SignTransactionsRequest:
        def check_msg_type():
            if ctx.msg_type != SignTransactionsRequest.message_type():
                raise SignTransactionsFailure(
                    code=ErrCode.InvalidMessage,
                    message=f"invalid message type: {ctx.msg_type}",
                )

        def unpack_request() -> SignTransactionsRequest:
            check_msg_type()
            try:
                return SignTransactionsRequest.unpack(ctx.msg_data)
            except Exception as err:
                raise SignTransactionsFailure(
                    code=ErrCode.InvalidMessage,
                    message=f"failed to unpack SignTransactionsRequest: {err}",
                )

        def check_request_required_fields(request: SignTransactionsRequest):
            raise NotImplementedError

        def check_service_fee_payment(payment: PaymentTxn):
            """
            Check payment for service fee
            """
            raise NotImplementedError

        def check_app_registration(app_id: AppId):
            """
            Check that the app is registered with the MultisigService
            """
            raise NotImplementedError

        def check_signer_opted_in(app_id: AppId, account: Address):
            """"
            Check that the signer is opted into the app
            """
            raise NotImplementedError

        request = unpack_request()
        check_request_required_fields(request)
        check_service_fee_payment(request.service_fee)
        check_app_registration(request.app_id)
        check_signer_opted_in(request.app_id, request.signer)

        return request
