import base64
from typing import NewType

from algosdk import constants, mnemonic
from algosdk.encoding import encode_address, decode_address
from nacl.exceptions import BadSignatureError
from nacl.public import PrivateKey, Box, PublicKey
from nacl.signing import SigningKey, SignedMessage, VerifyKey
from nacl.utils import EncryptedMessage

from oysterpack.algorand.client.model import Address, Mnemonic

# public box encryption key encoded as a base32 address
EncryptionAddress = NewType("EncryptionAddress", Address)

# public signing key encoded as a base32 address
SigningAddress = NewType("SigningAddress", Address)


class AlgoPrivateKey(PrivateKey):
    """
    Algorand private key can be used to sign and encrypt messages.

    Messages are encrypted using box encryption using the recipient's encryption address.
    The encrypted message can only be decrypted by the intended recipient using its private key
    and the senser's public EncryptionAddress.
    """

    def __init__(self, algo_private_key: str | bytes | Mnemonic):
        """
        :param algo_private_key: the Algorand account private key can be specified in the following formats:
                                 1. base64 encoded bytes
                                 2. raw bytes
                                 3. Mnemonic
        """
        if type(algo_private_key) is str:
            super().__init__(
                base64.b64decode(algo_private_key)[: constants.key_len_bytes]
            )
        elif type(algo_private_key) is bytes:
            super().__init__(algo_private_key[: constants.key_len_bytes])
        elif type(algo_private_key) is Mnemonic:
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
            mnemonic.from_private_key(base64.b64encode(bytes(self)))
        )

    @property
    def encryption_address(self) -> EncryptionAddress:
        """
        EncryptionAddress is derived from the Algorand account's private key.

        :return: base32 encoded public encryption key
        """
        return EncryptionAddress(encode_address(bytes(self.public_key)))

    @property
    def signing_key(self) -> SigningKey:
        return SigningKey(bytes(self))

    @property
    def signing_address(self) -> SigningAddress:
        """
        Signing address is the same as the Algorand address, which corresponds to the Algorand account public key.

        :return: base32 encoded public signing address
        """
        return SigningAddress(encode_address(bytes(self.signing_key.verify_key)))

    def encrypt(self, msg: bytes, recipient: EncryptionAddress) -> EncryptedMessage:
        return Box(self, encryption_address_to_public_key(recipient)).encrypt(msg)

    def decrypt(self, msg: EncryptedMessage, sender: EncryptionAddress) -> bytes:
        return Box(self, encryption_address_to_public_key(sender)).decrypt(
            msg.ciphertext, msg.nonce
        )

    def sign(self, msg: bytes) -> SignedMessage:
        return self.signing_key.sign(msg)


def encryption_address_to_public_key(address: EncryptionAddress) -> PublicKey:
    return PublicKey(decode_address(address))


def signing_address_to_verify_key(address: SigningAddress) -> VerifyKey:
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
