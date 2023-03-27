"""
Websockets Server
"""
import asyncio
from contextlib import asynccontextmanager
from ssl import SSLContext
from typing import Callable, Awaitable, Any

from websockets.legacy.server import WebSocketServerProtocol
from websockets.legacy.server import serve

from oysterpack.core.async_service import AsyncService

WebsocketHandler = Callable[[WebSocketServerProtocol], Awaitable[Any]]


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
        ssl_context: SSLContext | None = None,
    ):
        super().__init__()

        self.__handler = handler
        self.__port = port
        self.__ssl_context = ssl_context

    @property
    def port(self) -> int:
        """
        Port
        """
        return self.__port

    async def _start(self):
        self.__ws_server_stop_signal = asyncio.Future()

        async def run_ws_server():
            async with serve(self.__handler, port=self.__port, ssl=self.__ssl_context):  # type: ignore
                await self.__ws_server_stop_signal

        self.__ws_server_task = asyncio.create_task(run_ws_server())

    async def _stop(self):
        self.__ws_server_stop_signal.set_result(True)
        await self.__ws_server_task

    @asynccontextmanager
    async def start_server(self):
        await self.start()
        await self.await_running()
        await asyncio.sleep(0)
        try:
            yield self
        finally:
            await self.stop()
            await self.await_stopped()
