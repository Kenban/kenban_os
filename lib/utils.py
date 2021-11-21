import json
import logging
import os
import random
import string
from datetime import datetime, time
from distutils.util import strtobool
from os import getenv, utime
from platform import machine
from time import sleep
from urllib.parse import urlparse

import pytz
import redis
import requests

from settings import settings, LISTEN, PORT

WOTT_PATH = '/opt/wott'

WEEKDAY_DICT = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6
}

arch = machine()

# This will only work on the Raspberry Pi,
# so let's wrap it in a try/except so that
# Travis can run.
try:
    from sh import ffprobe
except ImportError:
    pass


def string_to_bool(string):
    return bool(strtobool(str(string)))


def touch(path):
    with open(path, 'a'):
        utime(path, None)


def is_ci():
    """
    Returns True when run on Travis.
    """
    return string_to_bool(os.getenv('CI', False))


def remove_connection(bus, uuid):
    """

    :param bus: pydbus.bus.Bus
    :param uuid: string
    :return: boolean
    """
    try:
        nm_proxy = bus.get("org.freedesktop.NetworkManager", "/org/freedesktop/NetworkManager/Settings")
    except Exception:
        return False

    nm_settings = nm_proxy["org.freedesktop.NetworkManager.Settings"]

    connection_path = nm_settings.GetConnectionByUuid(uuid)
    connection_proxy = bus.get("org.freedesktop.NetworkManager", connection_path)
    connection = connection_proxy["org.freedesktop.NetworkManager.Settings.Connection"]
    connection.Delete()

    return True


def handler(obj):
    # Set timezone as UTC if it's datetime and format as ISO
    if isinstance(obj, datetime):
        with_tz = obj.replace(tzinfo=pytz.utc)
        return with_tz.isoformat()
    else:
        raise TypeError('Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj)))


def json_dump(obj):
    return json.dumps(obj, default=handler)


def is_demo_node():
    """
    Check if the environment variable IS_DEMO_NODE is set to 1
    :return: bool
    """
    return string_to_bool(os.getenv('IS_DEMO_NODE', False))


def generate_perfect_paper_password(pw_length=10, has_symbols=True):
    """
    Generates a password using 64 characters from
    "Perfect Paper Password" system by Steve Gibson

    :param pw_length: int
    :param has_symbols: bool
    :return: string
    """
    ppp_letters = '!#%+23456789:=?@ABCDEFGHJKLMNPRSTUVWXYZabcdefghjkmnopqrstuvwxyz'
    if not has_symbols:
        ppp_letters = ''.join(set(ppp_letters) - set(string.punctuation))
    return "".join(random.SystemRandom().choice(ppp_letters) for _ in range(pw_length))


def connect_to_redis():
    return redis.Redis('redis')


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


def is_wott_integrated():
    """
    Chacks if wott-agent installed or not
    :return:
    """
    return os.path.isdir(WOTT_PATH)


def get_wott_device_id():
    """
    :return: WoTT Device id of this device
    """
    metadata_path = os.path.join(WOTT_PATH, 'metadata.json')
    if os.path.isfile(metadata_path):
        with open(metadata_path) as metadata_file:
            metadata = json.load(metadata_file)
        if 'device_id' in metadata:
            return metadata['device_id']
    logging.warning("Could not read WoTT Device ID")
    return 'Could not read WoTT Device ID'


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


def wait_for_server(retries: int, wt=1):
    for _ in range(retries):
        try:
            requests.get('http://{0}:{1}'.format(LISTEN, PORT))
            return True
        except requests.exceptions.ConnectionError:
            sleep(wt)
    return False


def get_wifi_status(retries=50, wt=0.1):
    wait_for_redis(200, 0.1)
    r = connect_to_redis()
    for _ in range(0, retries):
        try:
            wifi_status = r.get("wifi-status")
            if wifi_status:
                return int(wifi_status)
        except TypeError:
            sleep(wt)
    logging.error("Failed to wait for redis to start")