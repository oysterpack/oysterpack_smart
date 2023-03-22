"""
Websocket protocol
"""
from enum import IntEnum
from typing import Protocol, Iterable, AsyncIterable

Data = str | bytes


class CloseCode(IntEnum):
    """
    WebSocket close codes
    """

    # Normal close
    OK = 1000
    # Indicates a server side error has caused the connection to go away.
    GOING_AWAY = 1001


class Websocket(Protocol):
    """
    Websocket protocol
    """

    async def recv(self) -> Data:
        """
        Used to receive messages
        """
        ...

    async def send(
        self,
        message: Data | Iterable[Data] | AsyncIterable[Data],
    ) -> None:
        """
        Used to send messages
        """

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """
        Closes the websocket connetion

        :param code:
        :param reason:
        :return:
        """
