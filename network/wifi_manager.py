#!/usr/bin/python
import logging.config
import os
import random
import re
import signal
import subprocess
from datetime import datetime
from time import sleep

import redis
from netifaces import gateways, interfaces

r = redis.Redis("127.0.0.1", port=6379)
# FIXME There's a bug with the wifi connect UI creating 2 password fields

logging.config.fileConfig(fname='../logging.ini', disable_existing_loggers=True)
logger = logging.getLogger("wifi_manager")

def generate_password(pw_length=10):
    characters = 'ABCDEFGHJKLMNPRSTUVWXYZ'
    return "".join(random.SystemRandom().choice(characters) for _ in range(pw_length))


def generate_random_word_password(no_of_words=3):
    lines = open('wordlist.txt').read().splitlines()
    words = []
    for x in range(0, no_of_words):
        word = random.choice(lines)
        words.append(word)
    return "-".join(words)


def start_wifi_connect():
    logger.info("Creating hotspot with wifi-connect application")
    ssid = 'Kenban-{}'.format(generate_password(pw_length=4))
    ssid_password = generate_random_word_password(no_of_words=3)

    r.set("ssid", ssid)
    r.set("ssid-password", ssid_password)
    logger.debug(f"ssid {ssid}")
    logger.debug(f"password: {ssid_password}")

    args = ("./wifi-connect", "-s", ssid, "-p", ssid_password)
    process = subprocess.Popen(args, stdout=subprocess.PIPE)
    # todo test if this kills the process
    try:
        while True:
            if gateways().get('default'):
                os.kill(process.pid, signal.SIGINT)
                return True
            sleep(1)
    except:
        logger.error("Killing wifi-connect due to exception in wifi_manager.py")
        os.kill(process.pid, signal.SIGINT)


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
        logging.info("Connected detected on startup")
        return

    elif any(re.compile("wlan*").match(i) for i in interfaces()):
        # Check for a wireless interface and start wifi connect if so
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
            logging.debug("Connected")
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
    # FIXME On first startup this basically waits for 10 seconds and assumes that NetworkManager is set up by then.
    #  Briefly tried implementing the pydbus connection like in screenly, but couldn't get it working
    for _ in range(0, retries):
        if gateways().get('default'):
            return
        else:
            sleep(wt)


if __name__ == "__main__":

    logging.basicConfig(filename='wifi_manager.log',
                        filemode='w',
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        level=logging.DEBUG,
                        datefmt='%Y-%m-%d %H:%M:%S')

    wait_for_network()
    wait_for_redis(500)
    initial_startup()
    # Start infinite loop
    monitoring_loop()
