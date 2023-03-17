"""
Websockets Server
"""
import asyncio
from typing import Callable, Awaitable, Any

import websockets

from oysterpack.core.async_service import AsyncService

# pylint: disable=no-member
WebsocketHandler = Callable[[websockets.WebSocketServerProtocol], Awaitable[Any]]  # type: ignore


class WebsocketsServer(AsyncService):
    """
    WebsocketsServer
    """

    __ws_server_stop_signal: asyncio.Future[bool] = asyncio.Future()
    __ws_server_task: asyncio.Task

    def __init__(
        self,
        handler: WebsocketHandler,
        port: int = 8008,
    ):
        super().__init__()

        self.__handler = handler
        self.__port = port

    @property
    def port(self) -> int:
        """
        Port
        """
        return self.__port

    async def _start(self):
        self.__ws_server_stop_signal = asyncio.Future()

        async def run_ws_server():
            async with websockets.serve(self.__handler, port=self.__port):  # type: ignore
                await self.__ws_server_stop_signal

        self.__ws_server_task = asyncio.create_task(run_ws_server())

    async def _stop(self):
        self.__ws_server_stop_signal.set_result(True)
        await self.__ws_server_task
