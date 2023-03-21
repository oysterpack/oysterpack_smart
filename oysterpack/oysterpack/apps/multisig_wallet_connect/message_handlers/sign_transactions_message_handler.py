"""
SignTransactionsRequest message handler
"""
from oysterpack.algorand.messaging.secure_message_handler import MessageContext


class SignTransactionsRequestMessageHandler:
    async def __call__(self, msg_ctx: MessageContext):
        raise NotImplementedError
