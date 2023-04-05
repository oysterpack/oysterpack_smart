"""
:type:`AlgoPrivateKey` adds the capability to encrypt private messages using the same Algorand private key that is used
to sign messages.

Specifically, :type:``AlgoPrivateKey`` supports authenticated encryption, i.e., box encryption:

https://doc.libsodium.org/public-key_cryptography/authenticated_encryption
"""

import base64
from dataclasses import dataclass
from typing import NewType

from algosdk import constants, mnemonic
from algosdk.account import generate_account
from algosdk.encoding import encode_address, decode_address
from nacl.exceptions import BadSignatureError
from nacl.public import PrivateKey, Box, PublicKey
from nacl.signing import SigningKey, SignedMessage, VerifyKey

from oysterpack.algorand.client.model import Address, Mnemonic

# public box encryption key encoded as a base32 address
EncryptionAddress = NewType("EncryptionAddress", Address)

# public signing key encoded as a base32 address
# standard Algorand address
SigningAddress = NewType("SigningAddress", Address)


@dataclass(slots=True)
class AlgoPublicKeys:
    signing_address: SigningAddress
    encryption_address: EncryptionAddress


class AlgoPrivateKey(PrivateKey):
    """
    Algorand private keys can be used to sign and encrypt messages.

    Messages are encrypted using box encryption using the recipient's encryption address.
    The encrypted message can only be decrypted by the intended recipient using its private key
    and the sender's public EncryptionAddress.

    NOTES
    -----
    - Self encrypted messages can be created, i.e., sender == recipient
    """

    def __init__(self, algo_private_key: str | bytes | Mnemonic | None = None):
        """
        :param algo_private_key: If not specified, then a new Algorand private key will be generated.
            The Algorand account private key can be specified in the following formats:
                1. base64 encoded bytes
                2. raw bytes
                3. Mnemonic
        """
        if algo_private_key is None:
            algo_private_key = generate_account()[0]

        if isinstance(algo_private_key, str):
            super().__init__(
                base64.b64decode(algo_private_key)[: constants.key_len_bytes]
            )
        elif isinstance(algo_private_key, bytes):
            super().__init__(algo_private_key[: constants.key_len_bytes])
        elif isinstance(algo_private_key, Mnemonic):
            super().__init__(
                base64.b64decode(algo_private_key.to_private_key())[
                    : constants.key_len_bytes
                ]
            )
        else:
            raise ValueError("invalid private_key type - must be str | bytes")

    @property
    def mnemonic(self) -> Mnemonic:
        """
        :return: Algorand private key encoded as a 25-word mnemonic
        """
        return Mnemonic.from_word_list(
            mnemonic.from_private_key(base64.b64encode(bytes(self)).decode())
        )

    @property
    def public_keys(self) -> AlgoPublicKeys:
        return AlgoPublicKeys(
            signing_address=self.signing_address,
            encryption_address=self.encryption_address,
        )

    @property
    def encryption_address(self) -> EncryptionAddress:
        """
        EncryptionAddress is derived from the Algorand account's private key.

        :return: base32 encoded public encryption key
        """
        return EncryptionAddress(Address(encode_address(bytes(self.public_key))))

    @property
    def signing_key(self) -> SigningKey:
        """
        NOTE: This is the same signing key used to sign Algorand transactions.

        :return: private key used to sign messages
        """
        return SigningKey(bytes(self))

    @property
    def signing_address(self) -> SigningAddress:
        """
        Signing address is the same as the Algorand address, which corresponds to the Algorand account public key.

        :return: base32 encoded public signing address
        """
        return SigningAddress(
            Address(encode_address(bytes(self.signing_key.verify_key)))
        )

    def encrypt(
        self,
        msg: bytes,
        recipient: EncryptionAddress | None = None,
    ) -> bytes:
        """
        Encrypts a message that can only be decrypted by the recipient's private key.

        :param recipient: if None, then recipient is set to self
        """
        return Box(
            self,
            encryption_address_to_public_key(
                recipient if recipient else self.encryption_address
            ),
        ).encrypt(msg)

    def decrypt(
        self,
        msg: bytes,
        sender: EncryptionAddress | None = None,
    ) -> bytes:
        """
        Decrypts a message that was encrypted by the sender.

        :param sender: if None, then sender is set to self
        """
        return Box(
            self,
            encryption_address_to_public_key(
                sender if sender else self.encryption_address
            ),
        ).decrypt(
            ciphertext=msg[Box.NONCE_SIZE :],
            nonce=msg[: Box.NONCE_SIZE],
        )

    def sign(self, msg: bytes) -> SignedMessage:
        """
        Signs the message.
        """
        return self.signing_key.sign(msg)


def encryption_address_to_public_key(address: EncryptionAddress) -> PublicKey:
    """
    EncryptionAddress -> PublicKey
    """
    return PublicKey(decode_address(address))


def signing_address_to_verify_key(address: SigningAddress) -> VerifyKey:
    """
    SigningAddress -> VerifyKey
    """
    return VerifyKey(decode_address(address))


def verify_message(message: bytes, signature: bytes, signer: SigningAddress) -> bool:
    """
    :return: True if the message has a valid signature
    """
    verify_key = VerifyKey(decode_address(signer))
    try:
        verify_key.verify(message, signature)
        return True
    except BadSignatureError:
        return False
