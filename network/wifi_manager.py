#!/usr/bin/python
import logging.config
import random
import re
import subprocess
from datetime import datetime
from pathlib import Path
from time import sleep

import redis
from netifaces import gateways, interfaces

r = redis.Redis("127.0.0.1", port=6379)

logs_path = Path("logs")
logs_path.mkdir(exist_ok=True)
logging.config.fileConfig(fname='../logging.ini', disable_existing_loggers=True)
logger = logging.getLogger("wifi_manager")

CONNECTING_MESSAGE = "Stopping access point"
USER_ON_PORTAL_MESSAGE = "User connected to the captive portal"
SUCCESS_MESSAGE = "Internet connectivity established"
PASSWORD_LENGTH_ERROR = "Password length should be at least"
FAILED_TO_CONNECT_ERROR = "Connection to access point not activated"


def start_wifi_connect():
    logger.info("Creating hotspot with wifi-connect application")
    args = ("./wifi-connect", "-s", "NoticeHome")
    process = subprocess.Popen(args, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
    while process.poll() is None:
        # Read the stdout to determine the status of wifi-connect
        line = process.stdout.readline().decode("utf-8")
        if line:
            logger.debug(line)
            if USER_ON_PORTAL_MESSAGE in line:
                r.set("wifi-connect-status", "user-on-portal")
            if CONNECTING_MESSAGE in line:
                r.set("wifi-connect-status", "connecting")
                logger.info("Connecting to Wi-Fi")
            if SUCCESS_MESSAGE in line:
                r.set("wifi-connect-status", "success")
                r.setbit("internet-connected", offset=0, value=1)
                logger.info("Connected")
                return True
            if PASSWORD_LENGTH_ERROR in line:
                r.set("wifi-connect-status", "user-error")
                logger.warning("Incorrect password entered")
            if FAILED_TO_CONNECT_ERROR in line:
                r.set("wifi-connect-status", "user-error")
                logger.warning("Failed to connect to Wi-Fi")
    # If we reach this point, wifi-connect has failed. Exit and retry
    exit()


def wait_for_redis(retries: int, wt=0.1):
    # Make sure the redis container has started up
    for _ in range(0, retries):
        try:
            r.ping()
            return
        except redis.exceptions.ConnectionError:
            sleep(wt)
    logger.error("Failed to wait for redis to start")


def initial_startup():
    if gateways().get('default'):
        # If there is a default connection, sleep
        r.setbit("internet-connected", offset=0, value=1)
        logger.info("Connection detected on startup")
        return

    elif any(re.compile("wlan*").match(i) for i in interfaces()):
        # Check for a wireless interface and start Wi-Fi connect if so
        r.setbit("internet-connected", offset=0, value=0)
        r.setbit("wifi-manager-connecting", offset=0, value=1)
        start_wifi_connect()
        logger.info("wifi-connect finished")
        r.setbit("internet-connected", offset=0, value=1)
        r.setbit("wifi-manager-connecting", offset=0, value=0)

    else:
        r.setbit("internet-connected", offset=0, value=0)
        logger.error("Could not find wireless connection")
        sleep(1)


def monitoring_loop():
    last_connected = None
    while True:
        if gateways().get('default'):
            r.setbit("internet-connected", offset=0, value=1)
            if last_connected:
                logger.info("Internet reconnected")
                last_connected = None
            logger.debug("Internet connected. wifi_manager sleeping...")
            sleep(10)
            continue
        else:
            r.setbit("internet-connected", offset=0, value=0)
            if not last_connected:
                last_connected = datetime.now()
                r.set("last-connected", last_connected.timestamp())
                logger.error("Internet disconnected")
            sleep(1)


def wait_for_network(retries=10, wt=1):
    for _ in range(0, retries):
        logger.debug("Waiting for NetworkManager")
        if gateways().get('default'):
            logger.debug("wait_for_network NetworkManager found")
            return
        else:
            sleep(wt)


if __name__ == "__main__":
    r.setbit("internet-connected", offset=0, value=0)
    r.set("wifi-connect-status", "starting")
    wait_for_network()
    wait_for_redis(500)
    initial_startup()
    # Start infinite loop
    monitoring_loop()
