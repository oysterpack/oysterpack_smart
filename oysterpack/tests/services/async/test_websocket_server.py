import asyncio
import logging
import unittest

import websockets
from websockets.legacy.server import WebSocketServerProtocol

from oysterpack.services.asyncio.websockets_server import WebsocketsServer
from tests.test_support import OysterPackIsolatedAsyncioTestCase

logger = logging.getLogger("WebsocketsServiceTestCase")


class WebsocketServerTestCase(OysterPackIsolatedAsyncioTestCase):
    async def test_start_stop(self) -> None:
        messages: list[str | bytes] = []

        async def handler(websocket: WebSocketServerProtocol):
            async for message in websocket:
                messages.append(message)
                logger.info("received message: %s", message)
                await websocket.send(message)

        ws_server = WebsocketsServer(handler)
        await ws_server.start()
        await ws_server.await_running()
        await asyncio.sleep(0)

        # pylint: disable=no-member
        async with websockets.connect(f"ws://localhost:{ws_server.port}") as websocket:  # type: ignore
            for i in range(1, 11):
                msg = f"msg #{i}"
                await websocket.send(msg)
                response = await websocket.recv()
                self.assertEqual(msg, response)
                logger.info("received response: %s", response)

        await ws_server.stop()
        await ws_server.await_stopped()

    async def test_binary_messages(self) -> None:
        messages: list[str | bytes] = []

        async def handler(websocket: WebSocketServerProtocol):
            async for message in websocket:
                messages.append(message)
                logger.info("received message: %s", message)
                await websocket.send(message)

        ws_server = WebsocketsServer(handler)
        await ws_server.start()
        await ws_server.await_running()
        await asyncio.sleep(0)

        # pylint: disable=no-member
        async with websockets.connect(f"ws://localhost:{ws_server.port}") as websocket:  # type: ignore
            for i in range(1, 11):
                msg = f"msg #{i}".encode()
                await websocket.send(msg)
                response = await websocket.recv()
                self.assertIsInstance(response, bytes)
                self.assertEqual(msg, response)
                logger.info("received response: %s", response)

        await ws_server.stop()
        await ws_server.await_stopped()


if __name__ == "__main__":
    unittest.main()
