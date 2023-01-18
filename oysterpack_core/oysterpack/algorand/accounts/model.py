"""
Algorand account domain model

https://developer.algorand.org/docs/get-details/accounts/
"""

from dataclasses import dataclass
from typing import NewType

from algosdk import mnemonic

# Algorand account address. The address is 58 characters long
# https://developer.algorand.org/docs/get-details/accounts/#transformation-public-key-to-algorand-address
Address = NewType("Address", str)


@dataclass(slots=True)
class Mnemonic:
    """Mnemonics are 25 word lists that represent private keys.

    PrivateKey <-> Mnemonic

    https://developer.algorand.org/docs/get-details/accounts/#transformation-private-key-to-25-word-mnemonic
    """

    word_list: tuple[
        str, str, str, str, str,
        str, str, str, str, str,
        str, str, str, str, str,
        str, str, str, str, str,
        str, str, str, str, str]

    @classmethod
    def from_word_list(cls, word_list: str) -> 'Mnemonic':
        return cls(tuple(word_list.strip().split()))  # type: ignore

    def __post_init__(self):
        """
        Check that the mnemonic is a 25 word list.

        :exception ValueError: if the mnemonic does not consist of 25 words
        """
        if len(self.word_list) != 25:
            raise ValueError('')

    def to_master_derivation_key(self):
        """Converts the word list to the base64 encoded KMD wallet master derivation key"""
        return mnemonic.to_master_derivation_key(str(self))

    def to_private_key(self):
        """Converts the word list to the base64 encoded account private key"""
        return mnemonic.to_private_key(str(self))

    def __str__(self) -> str:  return ' '.join(self.word_list)
