"""
Algorand domain model

https://developer.algorand.org/docs/get-details/accounts/
"""

from dataclasses import dataclass
from typing import NewType, Any

import algosdk.encoding
from algosdk import mnemonic

# Algorand account address. The address is 58 characters long
# https://developer.algorand.org/docs/get-details/accounts/#transformation-public-key-to-algorand-address
Address = NewType("Address", str)

AssetId = NewType("AssetId", int)

BoxKey = NewType("BoxKey", bytes)

MicroAlgos = NewType("MicroAlgos", int)

TxnId = NewType("TxnId", str)


class AppId(int):
    """
    Algorand smart contract application ID
    """

    def to_address(self) -> Address:
        """
        Generates the smart contract's Algorand address from its app ID
        """

        app_id_checksum = algosdk.encoding.checksum(b"appID" + self.to_bytes(8, "big"))
        return Address(algosdk.encoding.encode_address(app_id_checksum))


@dataclass(slots=True)
class Transaction:
    """
    Transaction info
    """

    id: TxnId  # pylint: disable=invalid-name
    confirmed_round: int
    note: str | None = None


@dataclass(slots=True)
class AssetHolding:
    """
    Account asset holding.
    """

    amount: int
    asset_id: AssetId
    is_frozen: bool

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "AssetHolding":
        """
        :param data: required keys: 'amount','asset-id, 'is-frozen'
        :return:
        """
        if "asset-holding" in data:
            data = data["asset-holding"]
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
        """
        :param word_list: 25 word whitespace delimited list
        """
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
