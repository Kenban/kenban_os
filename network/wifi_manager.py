#!/usr/bin/python
import logging
import random
import re
import subprocess
from datetime import datetime
from time import sleep

import redis
from netifaces import gateways, interfaces

r = redis.Redis("127.0.0.1", port=6379)

""" Handles the WiFi for the Pi.Runs natively on the Pi and checks for network info. If no  """

def generate_password(pw_length=10):
    characters = 'ABCDEFGHJKLMNPRSTUVWXYZ'
    return "".join(random.SystemRandom().choice(characters) for _ in range(pw_length))


def generate_random_word_password(no_of_words=1, min_length=8):
    lines = open('/usr/share/dict/words').read().splitlines()
    words = []
    for x in range(0, no_of_words):
        word = random.choice(lines)
        while '\'' in word or len(word) < min_length:  # Don't use a word with an apostrophe
            word = random.choice(lines)
        words.append(word)
    return "-".join(words)


def start_wifi_connect():
    logging.info("Creating hotspot with wifi-connect application")
    ssid = 'Kenban-{}'.format(generate_password(pw_length=4))
    ssid_password = generate_random_word_password(no_of_words=1, min_length=8)

    r.set("ssid", ssid)
    r.set("ssid-password", ssid_password)
    logging.debug(f"ssid {ssid}")
    logging.debug(f"password: {ssid_password}")

    args = ("./wifi-connect", "-s", ssid, "-p", ssid_password)
    subprocess.Popen(args, stdout=subprocess.PIPE)
    while True:
        if gateways().get('default'):
            return True
        sleep(1)


def wait_for_redis(retries: int, wt=0.1):
    # Make sure the redis container has started up
    for _ in range(0, retries):
        try:
            r.ping()
            return
        except redis.exceptions.ConnectionError:
            sleep(wt)
    logging.error("Failed to wait for redis to start")


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
        logging.info("wifi-connect finished")
        r.setbit("internet-connected", offset=0, value=1)
        r.setbit("wifi-manager-connecting", offset=0, value=0)

    else:
        r.setbit("internet-connected", offset=0, value=0)
        logging.error("Could not find wireless connection")
        sleep(1)


def monitoring_loop():
    last_connected = None
    while True:
        if gateways().get('default'):
            r.setbit("internet-connected", offset=0, value=1)
            if last_connected:
                logging.info("Internet reconnected")
                last_connected = None
            logging.debug("Connected")
            sleep(10)
            continue
        else:
            r.setbit("internet-connected", offset=0, value=0)
            if not last_connected:
                last_connected = datetime.now()
                r.set("last-connected", last_connected.timestamp())
                logging.error("Internet disconnected")
            sleep(1)


if __name__ == "__main__":

    logging.basicConfig(filename='wifi_manager.log',
                        filemode='w',
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        level=logging.DEBUG,
                        datefmt='%Y-%m-%d %H:%M:%S')

    sleep(10)  # fixme This is here to allow the network to start up or we will create a hotspot every time. This isn't ideal
    wait_for_redis(500)
    initial_startup()
    # Start infinite loop
    monitoring_loop()
