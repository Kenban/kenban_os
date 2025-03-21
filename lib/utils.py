import json
import logging.config
import os
import socket
import string
import struct
from datetime import datetime, time
from distutils.util import strtobool
from time import sleep

import redis
import requests

from settings import settings

logging.config.fileConfig(fname='logging.ini', disable_existing_loggers=True)

WEEKDAY_DICT = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6
}

redis_pool = redis.ConnectionPool(host='localhost')


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


def wait_for_wifi_manager(retries=50, wt=0.1) -> bool:
    logging.info("Waiting for wifi_manager to startup")
    wait_for_redis(200, 0.1)
    r = connect_to_redis()
    for _ in range(0, retries):
        if r.getbit("internet-connected", 0) or r.getbit("wifi-manager-connecting", 0):
            return True
        else:
            sleep(wt)
    logging.error("Failed to get wifi-status")
    return False


def wait_for_internet_ping(retries=500, wt=0.1) -> bool:
    """ Attempt to reach 1.1.1.1 before continuing """
    host = socket.gethostbyname("1.1.1.1")
    for _ in range(0, retries):
        try:
            s = socket.create_connection((host, 80), 2)
            s.close()
            return True
        except OSError:
            sleep(wt)
    logging.error("Failed to ping 1.1.1.1")
    return False


def force_ntp_update():
    """ Connect to NTP server and set system time. Used because the system time wasn't being set in time for the
    startup sync causing SSL certificate errors"""

    unix_epoch = 2208988800  # difference between Unix and NTP epoch time
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    data = b'\x1b' + 47 * b'\0'
    client.sendto(data, ('0.uk.pool.ntp.org', 123))
    data, address = client.recvfrom(1024)
    if data:
        t = struct.unpack('!12I', data)[10]
        t -= unix_epoch
    else:
        logging.error("Failed to get time from NTP server. Waiting 30 seconds")
        sleep(30)
    dt = datetime.fromtimestamp(t)
    date_string = dt.strftime('%Y-%m-%d %H:%M:%S')
    os.system(f"sudo date -s '{date_string}'")


def wait_for_startup_sync(retries=5000, wt=0.1):
    r = connect_to_redis()
    for _ in range(0, retries):
        if r.exists("startup-sync-completed"):
            return True
        else:
            sleep(wt)
    logging.error("Failed to wait for startup sync")


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
