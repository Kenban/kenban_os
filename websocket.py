import asyncio
import json
import logging

import websockets
import socket
from websockets.exceptions import WebSocketException

import sync
from authentication import get_access_token
from lib.db_helper import create_or_update_schedule_slot, create_or_update_event
from lib.models import Session
from lib.utils import connect_to_redis
from settings import settings


async def subscribe_to_updates():
    """ Open a websocket connection with the server. When the string 'updated' is sent, trigger a sync of assets """
    while True:
        # Don't try and open a websocket if we don't have a device uuid yet
        if settings["device_uuid"] in [None, "None", ""]:
            logging.warning("Unable to start websocket: No device UUID")
            await asyncio.sleep(5)
            continue
        url = settings["websocket_updates_address"] + settings["device_uuid"]
        # outer loop restarted every time the connection fails
        try:
            async with websockets.connect(url) as ws:
                # Send the access token to authenticate
                logging.info("Attempting to connect to websocket")
                try:
                    access_token = get_access_token()
                    logging.debug(access_token)
                    await ws.send(access_token)
                    auth_response = await asyncio.wait_for(ws.recv(), timeout=10)
                    logging.info(f"Authentication response: {auth_response}")
                    if auth_response != "success":
                        r = connect_to_redis()
                        r.setbit("websocket-connected", offset=0, value=0)
                        logging.error("Failed to authenticate websocket")
                except (asyncio.TimeoutError, websockets.ConnectionClosed):
                    r = connect_to_redis()
                    r.setbit("websocket-connected", offset=0, value=0)
                    logging.error("Error authenticating websocket")
                logging.info("Websocket connected")
                while True:
                    r = connect_to_redis()
                    try:
                        r.setbit("websocket-connected", offset=0, value=1)
                        msg = await asyncio.wait_for(ws.recv(), timeout=10)
                        message_handler(msg)
                    except (asyncio.TimeoutError, websockets.ConnectionClosed):
                        # If we lose the connection, ping the server
                        try:
                            pong = await ws.ping()
                            await asyncio.wait_for(pong, timeout=10)
                            logging.debug('Ping OK, keeping connection alive...')
                            continue
                        except:
                            # Break to the outer loop if the ping fails and try to reconnection
                            r.setbit("websocket-connected", offset=0, value=0)
                            await asyncio.sleep(9)
                            break
        except (socket.gaierror, ConnectionRefusedError, OSError, WebSocketException) as e:
            r = connect_to_redis()
            r.setbit("websocket-connected", offset=0, value=0)
            logging.error("Websocket error")
            logging.error(e)
            await asyncio.sleep(9)
            continue


def message_handler(msg):
    logging.debug(f"Received websocket message: {msg}")
    payload = json.loads(msg)
    message_type = payload["message_type"]
    if not message_type:
        return
    if message_type == "schedule_slot":
        with Session() as session:
            create_or_update_schedule_slot(session, payload)
            session.commit()
    if message_type == "event":
        with Session() as session:
            create_or_update_event(session, payload)
            session.commit()
    if message_type == "image":
        image_uuid = payload["image_uuid"]
        sync.get_image(image_uuid)


if __name__ == "__main__":
    settings.load()
    logging.getLogger().setLevel(logging.DEBUG if settings['debug_logging'] else logging.INFO)

    #sync.full_sync()
    asyncio.run(subscribe_to_updates())
