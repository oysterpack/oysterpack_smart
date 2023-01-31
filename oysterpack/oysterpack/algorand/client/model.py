"""
Algorand domain model

https://developer.algorand.org/docs/get-details/accounts/
"""

from dataclasses import dataclass
from typing import NewType, Self, Any

import algosdk.encoding
from algosdk import mnemonic

# Algorand account address. The address is 58 characters long
# https://developer.algorand.org/docs/get-details/accounts/#transformation-public-key-to-algorand-address
Address = NewType("Address", str)

AssetID = NewType("AssetID", int)

BoxKey = NewType("BoxKey", bytes)


class AppID(int):
    def to_address(self) -> Address:
        """
        Generates the smart contract's Algorand address from its app ID
        """

        app_id_checksum = algosdk.encoding.checksum(b"appID" + self.to_bytes(8, "big"))
        return algosdk.encoding.encode_address(app_id_checksum)


@dataclass(slots=True)
class AssetHolding:
    amount: int
    asset_id: AssetID
    is_frozen: bool

    # TODO: https://github.com/python/mypy/issues/14167 remove mypy ignore once mypy support Self
    @classmethod
    def from_data(cls, data: dict[str, Any]) -> Self:  # type: ignore
        """
        :param data: required keys: 'amount','asset-id, 'is-frozen'
        :return:
        """
        return cls(
            amount=data["amount"],
            asset_id=data["asset-id"],
            is_frozen=data["is-frozen"],
        )


@dataclass(slots=True)
class Mnemonic:
    """Mnemonics are 25 word lists that represent private keys.

    PrivateKey <-> Mnemonic

    https://developer.algorand.org/docs/get-details/accounts/#transformation-private-key-to-25-word-mnemonic
    """

    word_list: tuple[
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
    ]

    @classmethod
    def from_word_list(cls, word_list: str) -> "Mnemonic":
        return cls(tuple(word_list.strip().split()))  # type: ignore

    def __post_init__(self):
        """
        Check that the mnemonic is a 25 word list.

        :exception ValueError: if the mnemonic does not consist of 25 words
        """
        if len(self.word_list) != 25:
            raise ValueError("mnemonic must consist of 25 words")

    def to_master_derivation_key(self) -> str:
        """Converts the word list to the base64 encoded KMD wallet master derivation key"""
        return mnemonic.to_master_derivation_key(str(self))

    def to_private_key(self) -> str:
        """Converts the word list to the base64 encoded account private key"""
        return mnemonic.to_private_key(str(self))

    def __str__(self) -> str:
        return " ".join(self.word_list)
