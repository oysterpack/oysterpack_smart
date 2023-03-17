"""
Websocket protocol
"""
from typing import Protocol, Iterable, AsyncIterable

Data = str | bytes


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
