import asyncio
import logging

import websockets
import socket
from websockets.exceptions import WebSocketException

from settings import settings
from sync import full_sync


async def subscribe_to_updates():
    """ Open a websocket connection with the server. When the string 'updated' is sent, trigger a sync of assets """
    url = settings["websocket_updates_address"] + settings["device_uuid"]
    while True:
        # outer loop restarted every time the connection fails
        try:
            async with websockets.connect(url) as ws:
                print("Websocket connected")
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=10)
                        if "updated" in msg:
                            full_sync()
                    except (asyncio.TimeoutError, websockets.ConnectionClosed):
                        try:
                            pong = await ws.ping()
                            await asyncio.wait_for(pong, timeout=10)
                            logging.debug('Ping OK, keeping connection alive...')
                            continue
                        except:
                            await asyncio.sleep(9)
                            break  # inner loop
        except socket.gaierror:
            logging.error("Websocket error")
            await asyncio.sleep(9)
            continue
        except ConnectionRefusedError:
            logging.error("Websocket connection refused")
            await asyncio.sleep(9)
            continue
        except WebSocketException as e:
            logging.error(e)
            await asyncio.sleep(9)
            continue


if __name__ == "__main__":
    asyncio.run(subscribe_to_updates())
