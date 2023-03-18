"""
SecureMessage Client
"""
import asyncio
from concurrent.futures import Executor
from typing import cast

from websockets.legacy.client import WebSocketClientProtocol

from oysterpack.algorand.client.accounts.private_key import (
    AlgoPrivateKey,
    EncryptionAddress,
)
from oysterpack.algorand.messaging.secure_message import (
    EncryptedMessage,
    SignedEncryptedMessage,
)
from oysterpack.core.message import Serializable, Message


class SecureMessageClientError(Exception):
    """
    SecureMessageClient base exception
    """


class MessageSignatureVerificationFailed(SecureMessageClientError):
    """
    Message signature verification failed
    """


class SecureMessageClient:
    def __init__(
        self,
        websocket: WebSocketClientProtocol,
        private_key: AlgoPrivateKey,
        executor: Executor,
    ):
        """
        :param websocket:
        :param private_key:
        :param executor: used to run CPU intensive work outside the event loop

        NOTES
        -----
        - Due to the GIL, :type:`ThreadPoolExecutor` can typically only be used to make IO-bound functions non-blocking.
          However, for extension modules that release the GIL or alternative Python implementations that don’t have one,
          :type:`ThreadPoolExecutor` can also be used for CPU-bound functions.

          Otherwise, use :type:`ProcessPoolExecutor`
        """
        self.__websocket = websocket
        self.__private_key = private_key
        self.__executor = executor

    async def send(self, data: Serializable, recipient: EncryptionAddress):
        # run CPU intensive work via executor because we don't want to block the event loop
        # secure_message = await asyncio.to_thread(create_secure_message)
        secure_message = await asyncio.get_event_loop().run_in_executor(
            self.__executor,
            _create_secure_message,
            self.__private_key,
            data,
            recipient,
        )
        await self.__websocket.send(secure_message.pack())

    async def recv(self) -> Message:
        secure_msg_bytes = cast(bytes, await self.__websocket.recv())

        # run CPU intensive work via executor because we don't want to block the event loop
        return await asyncio.get_event_loop().run_in_executor(
            self.__executor, _unpack_message, self.__private_key, secure_msg_bytes
        )

    async def close(self):
        await self.__websocket.close()


def _create_secure_message(
    private_key: AlgoPrivateKey,
    data: Serializable,
    recipient: EncryptionAddress,
) -> SignedEncryptedMessage:
    msg = Message.create(data.message_type(), data.pack())
    secret_message = EncryptedMessage.encrypt(
        sender_private_key=private_key,
        recipient=recipient,
        msg=msg.pack(),
    )
    return SignedEncryptedMessage.sign(
        private_key=private_key,
        msg=secret_message,
    )


def _unpack_message(private_key: AlgoPrivateKey, secure_msg_bytes: bytes) -> Message:
    secure_msg = SignedEncryptedMessage.unpack(secure_msg_bytes)
    if not secure_msg.verify():
        raise MessageSignatureVerificationFailed()
    decrypted_msg = secure_msg.secret_msg.decrypt(private_key)
    return Message.unpack(decrypted_msg)
