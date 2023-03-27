"""
Provides websocket testing support
"""

import asyncio
from ssl import SSLContext
from typing import Iterable, AsyncIterable, cast

from oysterpack.algorand.messaging.websocket import Websocket, Data
from oysterpack.services.asyncio.websockets_server import (
    WebsocketsServer,
    WebsocketHandler,
)

__websocket_server_port = 8008


def create_websocket_server(
    handler: WebsocketHandler,
    ssl_context: SSLContext | None = None,
) -> WebsocketsServer:
    """
    When the WebSocketServer is closed, its port is still bound and cannot be resused.

    The workaround is to use different ports.
    """

    global __websocket_server_port

    __websocket_server_port += 1
    return WebsocketsServer(
        handler=handler, ssl_context=ssl_context, port=__websocket_server_port
    )


class WebsocketMock(Websocket):
    def __init__(self) -> None:
        self.request_queue: asyncio.Queue[Data] = asyncio.Queue()
        self.response_queue: asyncio.Queue[Data] = asyncio.Queue()
        self.closed = False

    async def recv(self) -> Data:
        msg = await self.request_queue.get()
        self.request_queue.task_done()
        return msg

    async def send(
        self,
        message: Data | Iterable[Data] | AsyncIterable[Data],
    ) -> None:
        await self.response_queue.put(cast(Data, message))

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True
        self.close_code = code
        self.close_reason = reason
