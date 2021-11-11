import asyncio
import json
import logging

import websockets
import socket
from websockets.exceptions import WebSocketException

from lib.db_helper import save_schedule_slot
from lib.models import Session
from settings import settings


async def subscribe_to_updates():
    """ Open a websocket connection with the server. When the string 'updated' is sent, trigger a sync of assets """
    while True:
        # Don't try and open a websocket if we don't have a device uuid yet
        if settings["device_uuid"] in [None, "None", ""]:
            await asyncio.sleep(30)
            continue
        url = settings["websocket_updates_address"] + settings["device_uuid"]
        # outer loop restarted every time the connection fails
        try:
            async with websockets.connect(url) as ws:
                print("Websocket connected")
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=10)
                        message_handler(msg)
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


def message_handler(msg):
    print(msg)
    payload = json.loads(msg)
    data_type = payload["message_type"]
    if not data_type:
        return

    if data_type == "schedule_slot":
        with Session() as session:
            save_schedule_slot(session, payload)
            session.commit()


if __name__ == "__main__":
    asyncio.run(subscribe_to_updates())
