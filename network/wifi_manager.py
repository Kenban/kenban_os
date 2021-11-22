#!/usr/bin/python
import logging
import random
import re
import subprocess
from time import sleep

import redis
from netifaces import gateways, interfaces

WIFI_DISCONNECTED = 0
WIFI_CONNECTED = 1
WIFI_CONNECTING = 2

r = redis.Redis("127.0.0.1", port=6379)


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
    popen = subprocess.Popen(args, stdout=subprocess.PIPE)
    r.set("wifi-status", WIFI_CONNECTING)
    popen.wait()


def wait_for_redis(retries: int, wt=0.1):
    # Make sure the redis container has started up
    for _ in range(0, retries):
        try:
            r.ping()
            return
        except redis.exceptions.ConnectionError:
            sleep(wt)
    logging.error("Failed to wait for redis to start")


if __name__ == "__main__":

    logging.basicConfig(filename='debug.log',
                        filemode='w',
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        level=logging.DEBUG,
                        datefmt='%Y-%m-%d %H:%M:%S')

    sleep(10)  # fixme This is here to allow the network to start up or we will create a hotspot every time. This isn't ideal

    while True:
        if gateways().get('default'):
            # If there is a default connection, sleep
            wait_for_redis(500)
            r.set("wifi-status", WIFI_CONNECTED)
            logging.debug("A connection already exists")
            sleep(60)
            continue
        elif any(re.compile("wlan*").match(i) for i in interfaces()):
            # Check for a wireless interface and start wifi connect if so
            wait_for_redis(500)
            start_wifi_connect()
            logging.info("wifi-connect finished")
            r.set("wifi-status", WIFI_CONNECTED)

        else:
            wait_for_redis(500)
            r.set("wifi-status", WIFI_DISCONNECTED)
            logging.warning("Could not find wireless connection")
