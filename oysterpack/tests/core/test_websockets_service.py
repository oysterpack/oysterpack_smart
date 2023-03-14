# pylint: disable=no-member

import logging
import unittest

import websockets
from reactivex import Subject, Observable
from reactivex.operators import observe_on
from websockets.legacy.server import WebSocketServerProtocol

from oysterpack.core.rx import default_scheduler
from oysterpack.core.service import ServiceCommand
from oysterpack.services.websockets_service import WebsocketServer
from tests.test_support import OysterPackIsolatedAsyncioTestCase

logger = logging.getLogger("WebsocketsServiceTestCase")


class WebsocketsServiceTestCase(OysterPackIsolatedAsyncioTestCase):
    async def test_start_stop(self) -> None:
        commands: Subject[ServiceCommand] = Subject()
        commands_observable: Observable[ServiceCommand] = commands.pipe(
            observe_on(default_scheduler)
        )

        messages: list[str | bytes] = []

        async def handler(websocket: WebSocketServerProtocol):
            async for message in websocket:
                messages.append(message)
                logger.info("received message: %s", message)
                await websocket.send(message)

        ws_server = WebsocketServer(ws_handler=handler, commands=commands_observable)

        ws_server.start()
        ws_server.await_running()

        async with websockets.connect(f"ws://localhost:{ws_server.ws_port}") as websocket:  # type: ignore
            for i in range(1, 11):
                msg = f"msg #{i}"
                await websocket.send(msg)
                response = await websocket.recv()
                self.assertEqual(msg, response)
                logger.info("received response: %s", response)

        ws_server.stop()
        ws_server.await_stopped()


if __name__ == "__main__":
    unittest.main()
