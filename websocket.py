import asyncio
import logging

import websockets

from kenban.settings_kenban import settings as k_settings
from kenban.sync import full_sync


async def subscribe_to_updates():
    """ Open a websocket connection with the server. When the string 'updated' is sent, trigger a sync of assets """
    url = k_settings["websocket_updates_address"] + k_settings["device_uuid"]
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
            continue
        except ConnectionRefusedError:
            logging.error("Websocket connection refused")
            continue


if __name__ == "__main__":
    import os
    print(os.getcwd())
    asyncio.run(subscribe_to_updates())
