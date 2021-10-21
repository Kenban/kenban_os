#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import re
import urllib.parse
from os import path, getenv, utime, system
from signal import signal, SIGALRM, SIGUSR1
from time import sleep

import pydbus
import requests
import sh
from netifaces import gateways

from authentication import register_new_client, poll_for_authentication
from lib.errors import SigalrmException
from lib.github import is_up_to_date
from lib.utils import get_active_connections, is_balena_app, get_node_ip, string_to_bool, connect_to_redis
from schedule import Scheduler
from lib.models import ScheduleSlot
from settings import settings, LISTEN, PORT

__license__ = "Dual License: GPLv2 and Commercial License"

SPLASH_DELAY = 60  # secs
EMPTY_PL_DELAY = 5  # secs

INITIALIZED_FILE = '/.kenban/initialized'
WATCHDOG_PATH = '/tmp/screenly.watchdog'

LOAD_SCREEN = 'http://{}:{}/{}'.format(LISTEN, PORT, 'static/img/loading.png')

current_browser_url = None
browser = None
loop_is_stopped = False
browser_bus = None
r = connect_to_redis()

HOME = None
db_conn = None

scheduler = None


def sigalrm(signum, frame):
    """
    Signal just throw an SigalrmException
    """
    raise SigalrmException("SigalrmException")


def sigusr1(signum, frame):
    """
    The signal interrupts sleep() calls, so the currently
    playing web or image asset is skipped.
    """
    logging.info('USR1 received, skipping.')


def skip_asset(back=False):
    if back is True:
        scheduler.reverse = True
    system('pkill -SIGUSR1 -f viewer.py')


def navigate_to_asset(asset_id):
    scheduler.extra_asset = asset_id
    system('pkill -SIGUSR1 -f viewer.py')


def stop_loop():
    global db_conn, loop_is_stopped
    loop_is_stopped = True
    skip_asset()
    db_conn = None


def play_loop():
    global loop_is_stopped
    loop_is_stopped = False


def watchdog():
    """Notify the watchdog file to be used with the watchdog-device."""
    if not path.isfile(WATCHDOG_PATH):
        open(WATCHDOG_PATH, 'w').close()
    else:
        utime(WATCHDOG_PATH, None)


def load_browser():
    global browser
    logging.info('Loading browser...')

    browser = sh.Command('ScreenlyWebview')(_bg=True, _err_to_out=True)
    while 'Screenly service start' not in str(browser.process.stdout):
        sleep(1)


def view_webpage(uri: str):
    global current_browser_url

    if browser is None or not browser.process.alive:
        load_browser()
    if current_browser_url is not uri:
        browser_bus.loadPage(uri)
        current_browser_url = uri
    logging.info('Current url is {0}'.format(current_browser_url))


def build_schedule_slot_uri(schedule_slot: ScheduleSlot) -> str:
    hostname = f"{settings['local_address']}"
    parameters = urllib.parse.quote(
        f"?foreground_image_uuid={schedule_slot.foreground_image_uuid}"
        f"&template_uuid={schedule_slot.template_uuid}"
        f"&display_text={schedule_slot.display_text}"
        f"&time_format={schedule_slot.time_format}")
    uri = hostname + parameters
    return uri


def view_image(uri):
    global current_browser_url

    if browser is None or not browser.process.alive:
        load_browser()
    if current_browser_url is not uri:
        browser_bus.loadImage(uri)
        current_browser_url = uri
    logging.info('Current url is {0}'.format(current_browser_url))

    if string_to_bool(getenv('WEBVIEW_DEBUG', '0')):
        logging.info(browser.process.stdout)


def load_settings():
    """
    Load settings and set the log level.
    """
    settings.load()
    logging.getLogger().setLevel(logging.DEBUG if settings['debug_logging'] else logging.INFO)


def asset_loop(scheduler):
    # Check for software updates
    disable_update_check = getenv("DISABLE_UPDATE_CHECK", False)
    if not disable_update_check:
        is_up_to_date()

    schedule_slot = scheduler.get_current_slot()

    if schedule_slot is None:
        logging.info('Playlist is empty. Sleeping for %s seconds', EMPTY_PL_DELAY)
        # todo what do we want to show when there is no asset?
        view_image(LOAD_SCREEN)
        sleep(EMPTY_PL_DELAY)
    else:
        uri = build_schedule_slot_uri(schedule_slot)
        view_webpage(uri)
        refresh_duration = settings['asset_refresh_duration']
        logging.info(f'Sleeping for {refresh_duration}')
        sleep(refresh_duration)


def setup():
    global HOME, db_conn, browser_bus
    HOME = getenv('HOME', '/home/pi')

    signal(SIGUSR1, sigusr1)
    signal(SIGALRM, sigalrm)

    load_settings()

    load_browser()
    bus = pydbus.SessionBus()
    browser_bus = bus.get('screenly.webview', '/Screenly')


def setup_hotspot():
    bus = pydbus.SessionBus()

    pattern_include = re.compile("wlan*")
    pattern_exclude = re.compile("ScreenlyOSE-*")

    wireless_connections = get_active_connections(bus)

    if wireless_connections is None:
        return

    wireless_connections = [
        c for c in wireless_connections
        if pattern_include.search(str(c['Devices'])) and not pattern_exclude.search(str(c['Id']))
    ]

    # Displays the hotspot page
    if not path.isfile(HOME + INITIALIZED_FILE) and not gateways().get('default'):
        if len(wireless_connections) == 0:
            url = 'http://{0}/hotspot'.format(LISTEN)
            view_webpage(url)

    # Wait until the network is configured
    while not path.isfile(HOME + INITIALIZED_FILE) and not gateways().get('default'):
        if len(wireless_connections) == 0:
            sleep(1)
            wireless_connections = [
                c for c in get_active_connections(bus)
                if pattern_include.search(str(c['Devices'])) and not pattern_exclude.search(str(c['Id']))
            ]
            continue
        if wireless_connections is None:
            sleep(1)
            continue
        break

    wait_for_node_ip(5)


def wait_for_node_ip(seconds):
    for _ in range(seconds):
        try:
            get_node_ip()
            break
        except Exception:
            sleep(1)


def wait_for_server(retries, wt=1):
    for _ in range(retries):
        try:
            requests.get('http://{0}:{1}'.format(LISTEN, PORT))
            break
        except requests.exceptions.ConnectionError:
            sleep(wt)


def main():
    global db_conn, scheduler
    setup()

    from settings import settings
    # Check to see if device is paired
    if settings["refresh_token"] in [None, "None"]:
        logging.info("Starting pairing")
        device_code, verification_uri = register_new_client()
        if device_code is None:
            url = 'http://{0}:{1}/connect-error'.format(LISTEN, PORT)
        else:
            url = 'http://{0}:{1}/pair?user_code={2}&verification_uri={3}' \
                .format(LISTEN, PORT, device_code, verification_uri)
        view_webpage(url)
        poll_for_authentication(device_code=device_code)
    else:
        logging.info("Device already paired")

    scheduler = Scheduler()

    wait_for_server(5)

    if not is_balena_app():
        setup_hotspot()

    if settings['show_splash']:
        url = 'http://{0}:{1}/splash-page'.format(LISTEN, PORT)
        view_webpage(url)
        sleep(SPLASH_DELAY)

    # We don't want to show splash-page if there are active assets but all of them are not available
    view_image(LOAD_SCREEN)

    logging.debug('Entering infinite loop.')
    while True:
        if loop_is_stopped:
            sleep(0.1)
            continue

        asset_loop(scheduler)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Viewer crashed.")
        raise
