import asyncio
import json
import logging.config
import socket
from datetime import datetime
from time import sleep

import websockets
from websockets.exceptions import WebSocketException

from lib import sync
from lib.authentication import get_access_token
from lib.db_helper import create_or_update_schedule_slot, create_or_update_event
from lib.models import Session
from lib.utils import connect_to_redis, wait_for_internet_ping
from settings import settings


from lib.models import Base, engine
Base.metadata.create_all(engine)

logging.config.fileConfig(fname='logging.ini', disable_existing_loggers=True)
logger = logging.getLogger("websocket")


r = connect_to_redis()


async def subscribe_to_updates():
    """ Open a websocket connection with the server """
    while True:
        url = settings["websocket_updates_address"] + settings["device_uuid"]
        logger.info(f"Websocket attempting to connect to {url}")
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
                logger.error("Websocket disconnected")
            logger.exception(e)
            await asyncio.sleep(9)
            continue


async def websocket_loop(ws):
    logger.info("Keeping websocket open")
    while True:
        try:
            r.setbit("websocket-connected", offset=0, value=1)
            if r.exists("websocket-dc-timestamp"):
                logger.info("Websocket reconnected")
                r.delete("websocket-dc-timestamp")
            msg = await asyncio.wait_for(ws.recv(), timeout=None)
            message_handler(msg)
        except Exception:
            r.setbit("websocket-connected", offset=0, value=0)
            logger.exception("Websocket error")
            await asyncio.sleep(9)
            return  # Close this loop


async def authenticate_websocket(ws):
    # Send the access token to authenticate
    logger.info("Attempting to authenticate websocket")
    try:
        access_token = get_access_token()
        await ws.send(access_token)
        auth_response = await asyncio.wait_for(ws.recv(), timeout=10)
        logger.info(f"Authentication response: {auth_response}")
        if auth_response != "success":
            r.setbit("websocket-connected", offset=0, value=0)
            logger.error("Failed to authenticate websocket")
    except (asyncio.TimeoutError, websockets.ConnectionClosed):
        r.setbit("websocket-connected", offset=0, value=0)
        logger.exception("Error authenticating websocket")
    logger.info("Websocket authenticated")


def message_handler(msg):
    logger.debug(f"Received websocket message: {msg}")
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
        # An image change needs a force refresh because the url doesn't change (which causes a refresh)
        r.set("refresh-browser", 1)


def wait_for_refresh_token(wt=5) -> bool:
    while True:
        settings.load()
        if settings["refresh_token"] in [None, "None", ""]:
            logger.debug("Websocket waiting to start: No refresh token")
            sleep(wt)
            continue
        else:
            return True
    return False


if __name__ == "__main__":
    settings.load()
    # Don't try and connect if we don't have a token yet
    wait_for_refresh_token()
    # Wait for an internet connection
    wait_for_internet_ping()
    if r.exists("new-setup"):
        # Allow the server to set up the new user before performing a sync
        sleep(5)

    sync.full_sync()
    r.set("startup-sync-completed", 1, 60)
    asyncio.run(subscribe_to_updates())
