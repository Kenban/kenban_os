#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import re
from datetime import datetime
from os import path, getenv, utime, system
from random import shuffle
from signal import signal, SIGALRM, SIGUSR1
from time import sleep

import pydbus
import requests
import sh
from netifaces import gateways

from kenban.authentication import register_new_client, poll_for_authentication
from lib import assets_helper
from lib import db
from lib.errors import SigalrmException
from lib.github import is_up_to_date
from lib.utils import get_active_connections, is_balena_app, get_node_ip, string_to_bool, connect_to_redis
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


def command_not_found():
    logging.error("Command not found")


def send_current_asset_id_to_server():
    consumer = ZmqConsumer()
    consumer.send({'current_asset_id': scheduler.current_asset_id})


class Scheduler(object):
    def __init__(self, *args, **kwargs):
        logging.debug('Scheduler init')
        self.assets = []
        self.counter = 0
        self.current_asset_id = None
        self.deadline = None
        self.extra_asset = None
        self.index = 0
        self.reverse = 0
        self.update_playlist()

    def get_next_asset(self):
        logging.debug('get_next_asset')

        if self.extra_asset is not None:
            asset = get_specific_asset(self.extra_asset)
            if asset and asset['is_processing'] == 0:
                self.current_asset_id = self.extra_asset
                self.extra_asset = None
                return asset
            logging.error("Asset not found or processed")
            self.extra_asset = None

        self.refresh_playlist()
        logging.debug('get_next_asset after refresh')
        if not self.assets:
            self.current_asset_id = None
            return None
        if self.reverse:
            idx = (self.index - 2) % len(self.assets)
            self.index = (self.index - 1) % len(self.assets)
            self.reverse = False
        else:
            idx = self.index
            self.index = (self.index + 1) % len(self.assets)
        logging.debug('get_next_asset counter %s returning asset %s of %s', self.counter, idx + 1, len(self.assets))
        if settings['shuffle_playlist'] and self.index == 0:
            self.counter += 1

        current_asset = self.assets[idx]
        self.current_asset_id = current_asset.get('asset_id')
        return current_asset

    def refresh_playlist(self):
        logging.debug('refresh_playlist')
        time_cur = datetime.utcnow()
        logging.debug('refresh: counter: (%s) deadline (%s) timecur (%s)', self.counter, self.deadline, time_cur)
        if self.get_db_mtime() > self.last_update_db_mtime:
            logging.debug('updating playlist due to database modification')
            self.update_playlist()
        elif settings['shuffle_playlist'] and self.counter >= 5:
            self.update_playlist()
        elif self.deadline and self.deadline <= time_cur:
            self.update_playlist()

    def update_playlist(self):
        logging.debug('update_playlist')
        self.last_update_db_mtime = self.get_db_mtime()
        (new_assets, new_deadline) = generate_asset_list()
        if new_assets == self.assets and new_deadline == self.deadline:
            # If nothing changed, don't disturb the current play-through.
            return

        self.assets, self.deadline = new_assets, new_deadline
        self.counter = 0
        # Try to keep the same position in the play list. E.g. if a new asset is added to the end of the list, we
        # don't want to start over from the beginning.
        self.index = self.index % len(self.assets) if self.assets else 0
        logging.debug('update_playlist done, count %s, counter %s, index %s, deadline %s', len(self.assets), self.counter, self.index, self.deadline)

    def get_db_mtime(self):
        # get database file last modification time
        try:
            return path.getmtime(settings['database'])
        except (OSError, TypeError):
            return 0


def get_specific_asset(asset_id):
    logging.info('Getting specific asset')
    return assets_helper.read(db_conn, asset_id)


def generate_asset_list():
    """Choose deadline via:
        1. Map assets to deadlines with rule: if asset is active then 'end_date' else 'start_date'
        2. Get nearest deadline
    """
    logging.info('Generating asset-list...')
    assets = assets_helper.read(db_conn)
    deadlines = [asset['end_date'] if assets_helper.is_active(asset) else asset['start_date'] for asset in assets]

    playlist = list(filter(assets_helper.is_active, assets))
    deadline = sorted(deadlines)[0] if len(deadlines) > 0 else None
    logging.debug('generate_asset_list deadline: %s', deadline)

    if settings['shuffle_playlist']:
        shuffle(playlist)

    return playlist, deadline


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


def view_webpage(uri):
    global current_browser_url

    if browser is None or not browser.process.alive:
        load_browser()
    if current_browser_url is not uri:
        browser_bus.loadPage(uri)
        current_browser_url = uri
    logging.info('Current url is {0}'.format(current_browser_url))


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
    disable_update_check = getenv("DISABLE_UPDATE_CHECK", False)
    if not disable_update_check:
        is_up_to_date()
    asset = scheduler.get_next_asset()

    if asset is None:
        logging.info('Playlist is empty. Sleeping for %s seconds', EMPTY_PL_DELAY)
        view_image(LOAD_SCREEN)
        sleep(EMPTY_PL_DELAY)

    elif path.isfile(asset['uri']) or (not url_fails(asset['uri']) or asset['skip_asset_check']):
        name, mime, uri = asset['name'], asset['mimetype'], asset['uri']
        logging.info('Showing asset %s (%s)', name, mime)
        logging.debug('Asset URI %s', uri)
        watchdog()

        if 'image' in mime:
            view_image(uri)
        elif 'web' in mime:
            view_webpage(uri)
        else:
            logging.error('Unknown MimeType %s', mime)

        if 'image' in mime or 'web' in mime:
            duration = int(asset['duration'])
            logging.info('Sleeping for %s', duration)
            sleep(duration)

    else:
        logging.info('Asset %s at %s is not available, skipping.', asset['name'], asset['uri'])
        sleep(0.5)


def setup():
    global HOME, db_conn, browser_bus
    HOME = getenv('HOME', '/home/pi')

    signal(SIGUSR1, sigusr1)
    signal(SIGALRM, sigalrm)

    load_settings()
    db_conn = db.conn(settings['database'])

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
        if not db_conn:
            load_settings()
            db_conn = db.conn(settings['database'])

        asset_loop(scheduler)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Viewer crashed.")
        raise
