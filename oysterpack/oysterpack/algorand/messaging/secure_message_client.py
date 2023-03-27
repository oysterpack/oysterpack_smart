"""
SecureMessage Client
"""
import asyncio
from concurrent.futures import Executor
from contextlib import asynccontextmanager
from typing import cast

from websockets.legacy.client import WebSocketClientProtocol

from oysterpack.algorand.client.accounts.private_key import (
    AlgoPrivateKey,
    EncryptionAddress,
)
from oysterpack.algorand.messaging.secure_message import (
    pack_secure_message,
    unpack_secure_message,
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
        secure_message = await asyncio.get_event_loop().run_in_executor(
            self.__executor,
            pack_secure_message,
            self.__private_key,
            data,
            recipient,
        )
        await self.__websocket.send(secure_message)

    async def recv(self) -> Message:
        secure_msg_bytes = cast(bytes, await self.__websocket.recv())

        # run CPU intensive work via executor because we don't want to block the event loop
        return await asyncio.get_event_loop().run_in_executor(
            self.__executor,
            unpack_secure_message,
            self.__private_key,
            secure_msg_bytes,
        )

    async def close(self):
        await self.__websocket.close()

    @asynccontextmanager
    async def context(self):
        try:
            yield self
        finally:
            await self.close()
