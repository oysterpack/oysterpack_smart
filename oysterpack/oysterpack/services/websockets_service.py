"""
Websockets Server
"""

# pylint: disable=no-member

import asyncio
from threading import Thread
from typing import Callable, Awaitable, Any

import websockets
from reactivex import Observable
from websockets.legacy.server import WebSocketServerProtocol

from oysterpack.core.service import Service, ServiceCommand


class WebsocketServer(Service):
    """
    Websocket Server
    """

    def __init__(
        self,
        ws_handler: Callable[[WebSocketServerProtocol], Awaitable[Any]],
        ws_port: int = 8001,
        commands: Observable[ServiceCommand] | None = None,
    ):
        """
        :param ws_handler: websocket connection handler
        """
        super().__init__(commands)

        self.__ws_handler = ws_handler
        self.ws_port = ws_port
        self.__ws_server_stop_signal = asyncio.Event()

    def _start(self):
        """
        Starts the websocket server in a background thread
        """

        async def run():
            async with websockets.serve(self.__ws_handler, port=self.ws_port):  # type: ignore
                await self.__ws_server_stop_signal.wait()

        Thread(target=asyncio.run, args=(run(),), name=self.name, daemon=True).start()

    def _stop(self):
        self.__ws_server_stop_signal.set()
