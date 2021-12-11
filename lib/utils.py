import json
import logging
import os
import string
from datetime import datetime, time
from distutils.util import strtobool
from os import getenv
from time import sleep

import redis
import requests

from settings import settings, LISTEN, PORT

WEEKDAY_DICT = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6
}

redis_pool = redis.ConnectionPool(host='redis')


def string_to_bool(s):
    return bool(strtobool(str(s)))


def is_ci():
    """
    Returns True when run on Travis.
    """
    return string_to_bool(os.getenv('CI', False))

def connect_to_redis():
    return redis.Redis(connection_pool=redis_pool)


def wait_for_redis(retries: int, wt=0.1):
    # Make sure the redis container has started up
    r = connect_to_redis()
    for _ in range(0, retries):
        try:
            r.ping()
            return
        except redis.exceptions.ConnectionError:
            sleep(wt)
    logging.error("Failed to wait for redis to start")


def is_docker():
    return os.path.isfile('/.dockerenv')


def is_balena_app():
    """
    Checks the application is running on Balena Cloud
    :return: bool
    """
    return bool(getenv('RESIN', False)) or bool(getenv('BALENA', False))


def get_db_mtime():
    # get database file last modification time
    try:
        return os.path.getmtime(settings['database'])
    except (OSError, TypeError):
        return 0


def time_parser(t) -> time:
    if type(t) == str:
        try:
            t = datetime.strptime(t, "%H:%M").time()
        except ValueError:
            pass
        try:
            t = datetime.strptime(t, "%H:%M:%S").time()
        except ValueError:
            logging.warning("Failed to parse time, setting to 00:00")
            t = time(0, 0)
        finally:
            return t
    elif type(t) == time:
        return t
    else:
        logging.warning("Failed to parse time, setting to 00:00")
        return time(0, 0)


def wait_for_server(retries: int, wt=1) -> bool:
    for _ in range(retries):
        try:
            requests.get('http://{0}:{1}'.format(LISTEN, PORT))
            return True
        except requests.exceptions.ConnectionError:
            sleep(wt)
    return False


def wait_for_wifi_manager(retries=50, wt=0.1) -> bool:
    wait_for_redis(200, 0.1)
    r = connect_to_redis()
    for _ in range(0, retries):
        if r.getbit("internet-connected", 0) or r.getbit("wifi-manager-connecting", 0):
            return True
        else:
            sleep(wt)
    logging.error("Failed to get wifi-status")
    return False


def wait_for_initial_sync(retries=500, wt=0.1):
    r = connect_to_redis()
    for _ in range(0, retries):
        if r.exists("initial-sync-completed"):
            return True
        else:
            sleep(wt)
    logging.error("Failed to wait for initial sync")


def kenban_server_request(url: string, method: string, data=None, headers=None, decode_json=True):
    logging.debug(f"Making {method} request to {url}")
    try:
        response = requests.request(url=url, method=method, data=data, headers=headers)
        response.raise_for_status()
        logging.debug(f"Response: {response.content}")
    except requests.exceptions.HTTPError:
        logging.exception(f"HTTP Error while reaching {url}")
        return None
    except requests.exceptions.ConnectionError:
        logging.exception(f"Could not connect to authorisation server at {url}")
        return None
    if decode_json:
        try:
            return json.loads(response.content)
        except ValueError:
            logging.exception(f"Error decoding JSON returned from {url}")
            return None
    else:
        return response.content
