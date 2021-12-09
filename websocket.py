import asyncio
import json
import logging
import os
import socket
from datetime import datetime
from time import sleep

import websockets
from websockets.exceptions import WebSocketException

import sync
from authentication import get_access_token
from lib.db_helper import create_or_update_schedule_slot, create_or_update_event
from lib.models import Session
from lib.utils import connect_to_redis
from settings import settings


async def subscribe_to_updates():
    """ Open a websocket connection with the server """
    while True:
        url = settings["websocket_updates_address"] + settings["device_uuid"]
        logging.info(f"Websocket attempting to connect to {url}")
        try:
            async with websockets.connect(url) as ws:
                await authenticate_websocket(ws)
                await websocket_loop(ws)
        except (socket.gaierror, ConnectionRefusedError, OSError, WebSocketException) as e:
            # Log error and wait before trying to reconnect
            r = connect_to_redis()
            r.setbit("websocket-connected", offset=0, value=0)
            if not r.exists("websocket-dc-timestamp"):
                last_ws_connection = datetime.now()
                r.set("websocket-dc-timestamp", last_ws_connection.timestamp())
                logging.error("Websocket disconnected")
            logging.exception(e)
            await asyncio.sleep(9)
            continue


async def websocket_loop(ws):
    logging.info("Keeping websocket open")
    while True:
        try:
            r = connect_to_redis()
            r.setbit("websocket-connected", offset=0, value=1)
            if r.exists("websocket-dc-timestamp"):
                logging.info("Websocket reconnected")
                r.delete("websocket-dc-timestamp")
            msg = await asyncio.wait_for(ws.recv(), timeout=None)
            message_handler(msg)
        except Exception:
            r = connect_to_redis()
            r.setbit("websocket-connected", offset=0, value=0)
            logging.exception("Websocket error")
            await asyncio.sleep(9)
            return  # Close this loop


async def authenticate_websocket(ws):
    # Send the access token to authenticate
    logging.info("Attempting to authenticate websocket")
    try:
        access_token = get_access_token()
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
        logging.exception("Error authenticating websocket")
    logging.info("Websocket authenticated")


def message_handler(msg):
    logging.debug(f"Received websocket message: {msg}")
    payload = json.loads(msg)
    message_type = payload["message_type"]
    if not message_type:
        return
    if message_type == "schedule_slot":
        with Session() as session:
            sync.ensure_images_and_templates_in_local_storage(payload)
            create_or_update_schedule_slot(session, payload)
            session.commit()
    if message_type == "event":
        with Session() as session:
            sync.ensure_images_and_templates_in_local_storage(payload)
            create_or_update_event(session, payload)
            session.commit()
    if message_type == "image":
        image_uuid = payload["image_uuid"]
        sync.get_image(image_uuid)
        r = connect_to_redis()
        # Browser always refreshes if event/slot changes, because this alters the url. Need to force one for images
        r.set("refresh-browser", True)


def wait_for_device_uuid(retries: int, wt=1) -> bool:
    for _ in range(retries):
        if settings["device_uuid"] in [None, "None", ""]:
            logging.warning("Waiting websocket: No device UUID")
            sleep(wt)
            continue
        else:
            return True
    return False


if __name__ == "__main__":
    settings.load()
    logging.getLogger().setLevel(logging.DEBUG if settings['debug_logging'] else logging.INFO)

    # sync.full_sync()

    # Don't try and open a websocket if we don't have a device uuid yet
    wait_for_device_uuid(retries=100)
    asyncio.run(subscribe_to_updates())
