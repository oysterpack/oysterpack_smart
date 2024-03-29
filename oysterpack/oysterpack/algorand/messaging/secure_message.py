"""
Provides support secure messaging
"""
from dataclasses import dataclass
from typing import Self, overload

import msgpack  # type: ignore
from nacl.exceptions import CryptoError

from oysterpack.algorand.client.accounts.private_key import (
    SigningAddress,
    EncryptionAddress,
    AlgoPrivateKey,
    verify_message,
)
from oysterpack.core.message import Serializable, Message, MessageId


@dataclass(slots=True)
class EncryptedMessage:
    """
    Encrypted message
    """

    sender: EncryptionAddress
    recipient: EncryptionAddress
    encrypted_msg: bytes

    @classmethod
    def encrypt(
        cls,
        sender_private_key: AlgoPrivateKey,
        recipient: EncryptionAddress,
        msg: bytes,
    ) -> Self:
        """
        Creates encrypted message
        """
        return cls(
            sender=sender_private_key.encryption_address,
            recipient=recipient,
            encrypted_msg=sender_private_key.encrypt(msg, recipient),
        )

    def decrypt(self, recipient_private_key: AlgoPrivateKey) -> bytes:
        """
        Decrypts the message
        """
        return recipient_private_key.decrypt(self.encrypted_msg, self.sender)


@dataclass
class SignedEncryptedMessage:
    """
    Message is signed and encrypted using the same underlying private key.
    """

    sender: SigningAddress
    signature: bytes
    encrypted_msg: EncryptedMessage

    @classmethod
    def sign(cls, private_key: AlgoPrivateKey, msg: EncryptedMessage) -> Self:
        """
        Signs the encrypted message
        """
        return cls(
            sender=private_key.signing_address,
            signature=private_key.sign(msg.encrypted_msg).signature,
            encrypted_msg=msg,
        )

    def verify(self) -> bool:
        """
        :return: True if the message signature passed verification
        """
        return verify_message(
            message=self.encrypted_msg.encrypted_msg,
            signature=self.signature,
            signer=self.sender,
        )

    @classmethod
    def unpack(cls, msg: bytes) -> Self:
        """
        Deserializes the msg into a SecureMessage
        """
        (
            sender,
            signature,
            secret_msg_sender,
            secret_msg_recipient,
            secret_msg_encrypted_msg,
        ) = msgpack.unpackb(msg, use_list=False)

        return cls(
            sender=sender,
            signature=signature,
            encrypted_msg=EncryptedMessage(
                sender=secret_msg_sender,
                recipient=secret_msg_recipient,
                encrypted_msg=secret_msg_encrypted_msg,
            ),
        )

    def pack(self) -> bytes:
        """
        Serialized the message into bytes
        """
        return msgpack.packb(
            (
                self.sender,
                self.signature,
                self.encrypted_msg.sender,
                self.encrypted_msg.recipient,
                self.encrypted_msg.encrypted_msg,
            )
        )


def create_secure_message(
    private_key: AlgoPrivateKey,
    data: Serializable,
    recipient: EncryptionAddress,
    msg_id: MessageId | None = None,
) -> SignedEncryptedMessage:
    """
    Constructs a SignedEncryptedMessage and serializes it
    """
    msg = Message(
        msg_id=MessageId() if msg_id is None else msg_id,
        msg_type=data.message_type(),
        data=data.pack(),
    )
    secret_message = EncryptedMessage.encrypt(
        sender_private_key=private_key,
        recipient=recipient,
        msg=msg.pack(),
    )
    return SignedEncryptedMessage.sign(
        private_key=private_key,
        msg=secret_message,
    )


def pack_secure_message(
    private_key: AlgoPrivateKey,
    data: Serializable,
    recipient: EncryptionAddress,
    msg_id: MessageId | None = None,
) -> bytes:
    """
    Constructs a SignedEncryptedMessage and serializes it
    """
    return create_secure_message(
        private_key=private_key,
        data=data,
        recipient=recipient,
        msg_id=msg_id,
    ).pack()


class InvalidSecureMessage(Exception):
    """
    InvalidSecureMessage
    """


class MessageSignatureVerificationFailed(InvalidSecureMessage):
    """
    Message signature verification failed
    """


class DecryptionFailed(InvalidSecureMessage):
    """
    DecryptionFailed
    """


@overload
def unpack_secure_message(
    private_key: AlgoPrivateKey,
    secure_msg: SignedEncryptedMessage,
) -> Message:
    """
    overlaod for SignedEncryptedMessage instance
    """


@overload
def unpack_secure_message(
    private_key: AlgoPrivateKey,
    secure_msg: bytes,
) -> Message:
    """
    overlaod for SignedEncryptedMessage bytes
    """


def unpack_secure_message(
    private_key: AlgoPrivateKey,
    secure_msg: bytes | SignedEncryptedMessage,
) -> Message:
    """
    1. If :param:`secure_msg` is bytes, then deserialize it into s SignedEncryptedMessage
    2. verifies the signature
    3. decrypts the message
    4. Deserializes the decrypted message into a Message
    """

    if isinstance(secure_msg, bytes):
        try:
            secure_msg = SignedEncryptedMessage.unpack(secure_msg)
        except Exception as err:
            raise InvalidSecureMessage(
                "failed to unpack SignedEncryptedMessage"
            ) from err

    if not secure_msg.verify():
        raise MessageSignatureVerificationFailed()

    try:
        decrypted_msg = secure_msg.encrypted_msg.decrypt(private_key)
    except CryptoError as err:
        raise DecryptionFailed() from err

    try:
        return Message.unpack(decrypted_msg)
    except Exception as err:
        raise InvalidSecureMessage("failed to unpack Message") from err
