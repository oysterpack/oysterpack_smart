"""
Messages for signing Algorand transactions
"""
from dataclasses import dataclass, field
from typing import ClassVar

from ulid import ULID

from oysterpack.algorand.client.accounts.private_key import SigningAddress
from oysterpack.algorand.client.model import AppId
from oysterpack.core.message import Serializable, MessageType

RequestId = ULID
Signature = bytes


@dataclass(slots=True)
class SignTransactionsRequest(Serializable):
    # unique request ID
    request_id: RequestId

    # app that has submitted the request
    #
    # Notes
    # -----
    # - this message's packed bytes must be signed by the app's creator auth account
    app_id: AppId

    # account that is being requested to sign the transactions
    signer: SigningAddress

    MSG_TYPE: ClassVar[MessageType] = field(
        default=MessageType.from_str("01GVXV7CQQY4Q0SSW6GBJCN192"),
        init=False,
        repr=False,
    )

    @classmethod
    def message_type(cls) -> MessageType:
        return cls.MSG_TYPE
