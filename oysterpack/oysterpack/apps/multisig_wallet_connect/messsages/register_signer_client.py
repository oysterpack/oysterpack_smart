"""
Messages used by the signer client to register with the Multisig Service
"""
from dataclasses import dataclass
from typing import Self, ClassVar

import msgpack  # type: ignore

from oysterpack.algorand.client.accounts.private_key import SigningAddress
from oysterpack.algorand.client.model import Address
from oysterpack.core.message import Serializable, MessageType


@dataclass(slots=True)
class RegisterSignerClient(Serializable):
    """
    Used to register a multisig signer for an asset holding account.
    """

    MSG_TYPE: ClassVar[MessageType] = MessageType.from_str("01GW9NMCCZD3PRR65ANF6BBXV7")

    # asset holding account
    account: Address
    # asset hol
    multisig_signer: SigningAddress

    @classmethod
    def message_type(cls) -> MessageType:
        return cls.MSG_TYPE

    @classmethod
    def unpack(cls, packed: bytes) -> Self:
        """
        Unpacks the packed bytes into a new instance of Self
        """
        (account, multisig_signer) = msgpack.unpackb(packed)
        return cls(
            account=account,
            multisig_signer=multisig_signer,
        )

    def pack(self) -> bytes:
        """
        Packs the object into bytes
        """
        return msgpack.packb(
            (
                self.account,
                self.multisig_signer,
            )
        )
