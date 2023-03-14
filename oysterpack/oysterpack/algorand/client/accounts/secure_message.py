"""
Provides support secure messaging
"""
from dataclasses import dataclass

import msgpack  # type: ignore
from nacl.utils import EncryptedMessage

from oysterpack.algorand.client.accounts.private_key import (
    SigningAddress,
    EncryptionAddress,
    AlgoPrivateKey,
    verify_message,
)


@dataclass(slots=True)
class SecretMessage:
    """
    Encrypted message
    """

    sender: EncryptionAddress
    recipient: EncryptionAddress
    encrypted_msg: EncryptedMessage

    @classmethod
    def encrypt(
        cls,
        sender_private_key: AlgoPrivateKey,
        recipient: EncryptionAddress,
        msg: bytes,
    ) -> "SecretMessage":
        return cls(
            sender=sender_private_key.encryption_address,
            recipient=recipient,
            encrypted_msg=sender_private_key.encrypt(msg, recipient),
        )

    def decrypt(self, recipient_private_key: AlgoPrivateKey) -> bytes:
        return recipient_private_key.decrypt(self.encrypted_msg, self.sender)


@dataclass
class SecureMessage:
    """
    Message is signed and encrypted using the same underlying private key.
    """

    sender: SigningAddress
    signature: bytes
    secret_msg: SecretMessage

    @classmethod
    def sign(cls, private_key: AlgoPrivateKey, msg: SecretMessage) -> "SecureMessage":
        return cls(
            sender=private_key.signing_address,
            signature=private_key.sign(msg.encrypted_msg).signature,
            secret_msg=msg,
        )

    @classmethod
    def unpackb(cls, msg: bytes) -> "SecureMessage":
        (
            sender,
            signature,
            secret_msg_sender,
            secret_msg_recipient,
            secret_msg_nonce,
            secret_msg_ciphertext,
        ) = msgpack.unpackb(msg, use_list=False)

        return cls(
            sender=sender,
            signature=signature,
            secret_msg=SecretMessage(
                sender=secret_msg_sender,
                recipient=secret_msg_recipient,
                encrypted_msg=EncryptedMessage._from_parts(
                    nonce=secret_msg_nonce,
                    ciphertext=secret_msg_ciphertext,
                    combined=secret_msg_nonce + secret_msg_ciphertext,
                ),
            ),
        )

    def verify(self) -> bool:
        return verify_message(
            message=self.secret_msg.encrypted_msg,
            signature=self.signature,
            signer=self.sender,
        )

    def packb(self) -> bytes:
        return msgpack.packb(
            (
                self.sender,
                self.signature,
                self.secret_msg.sender,
                self.secret_msg.recipient,
                self.secret_msg.encrypted_msg.nonce,
                self.secret_msg.encrypted_msg.ciphertext,
            )
        )
