#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import urllib.parse
from os import getenv
from signal import signal, SIGALRM, SIGUSR1
from time import sleep

import requests

import sync
from authentication import register_new_client, poll_for_authentication, get_auth_header
from lib.browser_handler import BrowserHandler
from lib.errors import SigalrmException
from lib.models import ScheduleSlot
from lib.scheduler import Scheduler
from lib.utils import connect_to_redis, \
    get_db_mtime, wait_for_server, get_wifi_status
from network.wifi_manager import WIFI_CONNECTING, WIFI_DISCONNECTED, WIFI_CONNECTED
from settings import settings, LISTEN, PORT

__license__ = "Dual License: GPLv2 and Commercial License"

EMPTY_PL_DELAY = 5  # secs
SCREEN_TICK_DELAY = 0.1  # secs

INITIALIZED_FILE = '/.kenban/initialized'
WATCHDOG_PATH = '/tmp/screenly.watchdog'

LOAD_SCREEN = f'http://{LISTEN}:{PORT}/img/loading.png'
NEW_SETUP_SCREEN = f'http://{LISTEN}:{PORT}/img/new-setup.png'

HOME = None


def sigalrm():
    """
    Signal just throw an SigalrmException
    """
    raise SigalrmException("SigalrmException")


def sigusr1():
    """
    The signal interrupts sleep() calls, so the currently
    playing web or image asset is skipped.
    """
    logging.info('USR1 received, skipping.')


def build_schedule_slot_uri(schedule_slot: ScheduleSlot, event=None) -> str:
    hostname = f"{settings['local_address']}"

    # Add the info for the schedule slot
    if not schedule_slot:
        uri = hostname + "/splash-page"
        logging.warning("build_schedule_slot_uri called with no active slot")
        return uri
    url_parameters = {
        "foreground_image_uuid": schedule_slot.foreground_image_uuid,
        "template_uuid": schedule_slot.template_uuid,
        "display_text": schedule_slot.display_text if schedule_slot.display_text else "",
        "time_format": schedule_slot.time_format,
    }
    # Add the info for any event
    if event:
        url_parameters["event_text"] = event.display_text if event.display_text else ""
        url_parameters["event_image_uuid"] = event.foreground_image_uuid

    # Add any other info
    r = connect_to_redis()
    logging.info("new_setup:")
    if schedule_slot.display_text == "" and r.exists("new_setup"):
        url_parameters["display_text"] = "Visit kenban.co.uk to add a schedule your new device"
    if r.exists("banner"):
        url_parameters["banner"] = r.get("banner")

    url_parameters = urllib.parse.urlencode(url_parameters)
    uri = hostname + "/kenban?" + url_parameters
    return uri


def display_loop(browser_handler: BrowserHandler, scheduler: Scheduler):
    if scheduler.current_slot is None:
        logging.info('Playlist is empty. Sleeping for %s seconds', EMPTY_PL_DELAY)
        browser_handler.view_image(LOAD_SCREEN)
        sleep(EMPTY_PL_DELAY)
    else:
        logging.debug(f"Current schedule slot start time: {scheduler.current_slot.start_time}")
        event = None
        if scheduler.event_active:
            event = scheduler.active_events[0]  # Just get the first event for now, maybe change this later
        uri = build_schedule_slot_uri(scheduler.current_slot, event)
        browser_handler.view_webpage(uri)

    if get_db_mtime() > scheduler.last_update_db_mtime:
        scheduler.update_assets_from_db()
    scheduler.tick()
    sleep(SCREEN_TICK_DELAY)


def setup():
    global HOME
    HOME = getenv('HOME', '/home/pi')

    signal(SIGUSR1, sigusr1)
    signal(SIGALRM, sigalrm)

    settings.load()
    logging.getLogger().setLevel(logging.DEBUG if settings['debug_logging'] else logging.INFO)


def show_hotspot_page(browser_handler: BrowserHandler):
    r = connect_to_redis()
    ssid = r.get("ssid").decode("utf-8")
    ssid_password = r.get("ssid-password").decode("utf-8")
    logging.info("Displaying hotspot page")
    logging.info(f"SSID = {ssid}")
    logging.info(f"SSID Password = {ssid_password}")
    url = f'http://{LISTEN}/hotspot?ssid={ssid}&ssid_password={ssid_password}'
    wait_for_server(retries=5)
    browser_handler.view_webpage(url)

    # Stay in a loop until the wifi status changes
    wifi_status = get_wifi_status()
    while wifi_status == WIFI_CONNECTING:
        sleep(1)
        wifi_status = get_wifi_status()


def confirm_setup_completion():
    url = settings['server_address'] + settings['setup_complete'] + "/" + settings["device_uuid"]
    headers = get_auth_header()
    logging.debug(f"Confirming setup completion to {url}")
    try:
        response = requests.post(url=url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        logging.warning("HTTP Error confirming completion:" + str(error))
        return None
    except ConnectionError:
        logging.warning("Could not connect to authorisation server at {0}".format(url))
        return None


def device_pair(browser_handler: BrowserHandler):
    logging.info("Starting pairing")
    while True:
        device_code, verification_uri = register_new_client()
        if device_code is None:
            logging.error("Failed to register new client with server")
            show_error_page(browser_handler, "Error trying to contact Kenban server to register device")
            sleep(10)
            continue
        else:
            url = 'http://{0}:{1}/pair?user_code={2}&verification_uri={3}' \
                .format(LISTEN, PORT, device_code, verification_uri)
            browser_handler.view_webpage(url)
            auth_success = poll_for_authentication(device_code=device_code)
            if auth_success:
                logging.info("Device paired successfully")
                r = connect_to_redis()
                r.set("new_setup", "True", ex=3600)
                return
            else:
                logging.error("Authentication polling failed")
                show_error_page(browser_handler, "Authentication polling failed")
                sleep(10)
                continue


def show_error_page(browser_handler, error_message):
    error_message = urllib.parse.urlencode(error_message)
    browser_handler.view_webpage(f"http://{LISTEN}:{PORT}/error?message=" + error_message)


def main():
    from settings import settings
    setup()
    browser_handler = BrowserHandler()

    wifi_status = get_wifi_status()
    if wifi_status:
        while wifi_status != WIFI_CONNECTED:
            if wifi_status == WIFI_CONNECTING:
                show_hotspot_page(browser_handler)
            elif wifi_status == WIFI_DISCONNECTED:
                logging.warning("wifi-status = Disconnected")
                sleep(1)
            else:
                logging.critical("Invalid wifi-status from redis: " + str(wifi_status))
            wifi_status = get_wifi_status()
    else:
        if settings["refresh_token"] in [None, "None", ""]:
            # If device is paired, continue anyway
            r = connect_to_redis()
            r.set("wifi-error", True)
            logging.warning("Continuing without wifi setup")
        else:
            # If device isn't paired, we can't continue
            show_error_page(browser_handler, "Unable to start wifi manager. Please try restarting your device")

    if settings["refresh_token"] in [None, "None", ""]:
        wait_for_server(retries=5)
        device_pair(browser_handler)
        browser_handler.view_image(NEW_SETUP_SCREEN)
        sleep(10)  # Wait for the server to setup the new screen before continuing
        sync.full_sync()
        #confirm_setup_completion()
    else:
        logging.info(f"Device already paired")
        browser_handler.view_image(LOAD_SCREEN)

    scheduler = Scheduler()

    logging.debug('Entering infinite loop.')
    while True:
        display_loop(browser_handler=browser_handler, scheduler=scheduler)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Viewer crashed.")
        raise
