#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import urllib.parse
from datetime import datetime, timedelta
from os import getenv
from signal import signal, SIGALRM, SIGUSR1
from time import sleep
from typing import List

import pydbus
import requests
import sh

import sync
from authentication import register_new_client, poll_for_authentication, get_auth_header
from lib.errors import SigalrmException
from lib.models import ScheduleSlot, Session, Event
from lib.utils import string_to_bool, connect_to_redis, \
    get_db_mtime, WEEKDAY_DICT, wait_for_redis
from network.wifi_manager import WIFI_CONNECTING, WIFI_DISCONNECTED, WIFI_CONNECTED
from settings import settings, LISTEN, PORT

__license__ = "Dual License: GPLv2 and Commercial License"

EMPTY_PL_DELAY = 5  # secs
SCREEN_TICK_DELAY = 1  # secs

INITIALIZED_FILE = '/.kenban/initialized'
WATCHDOG_PATH = '/tmp/screenly.watchdog'

LOAD_SCREEN = f'http://{LISTEN}:{PORT}/img/loading.png'
NEW_SETUP_SCREEN = f'http://{LISTEN}:{PORT}/img/new-setup.png'

current_browser_url = None
browser = None
loop_is_stopped = False
browser_bus = None
r = connect_to_redis()

HOME = None

last_slot = None


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


class SlotHandler(object):
    def __init__(self):
        self.last_update_db_mtime = None
        self.slots: List[ScheduleSlot] = []
        self.current_slot = None
        self.current_slot_index = None
        self.next_slot = None
        self.events: List[Event] = []
        self.event_active = False
        self.active_events: List[Event] = []
        self.daily_events: List[Event] = []
        self.daily_events_date = None  # To check if events have been collected today
        self.update_assets_from_db()
        self.calculate_current_slot()
        self.calculate_daily_events()
        self.calculate_current_events()

    def set_current_slot(self, slot):
        if not slot:
            logging.debug(f"SlotHandler: No slot found")
            self.current_slot = None
            return
        logging.debug(f"Setting current slot to {slot.uuid}")
        self.current_slot = slot
        self.current_slot_index = self.slots.index(slot)
        # Check if it's the last in the list
        if len(self.slots) - 1 == self.current_slot_index:
            self.next_slot = self.slots[0]
        else:
            self.next_slot = self.slots[self.current_slot_index + 1]

    def sort_slots(self):
        """ Order the list of slots chronologically"""
        self.slots.sort(key=lambda s: s.start_time)
        self.slots.sort(key=lambda s: WEEKDAY_DICT[s.weekday])

    def tick(self):
        """ Check if it's time for the next slot in the order, and switch if so"""
        logging.debug("viewer tick")
        if not self.next_slot:
            logging.info("No next slot set")
        if WEEKDAY_DICT[self.next_slot.weekday] == datetime.now().weekday() and \
                datetime.now().time() > self.next_slot.start_time:
            self.set_current_slot(self.next_slot)

        if self.daily_events_date != datetime.now().date():
            self.calculate_daily_events()

        self.calculate_current_events()

    def calculate_current_slot(self):
        """ Return the slot that should currently be active according to times """
        this_weekday = datetime.now().strftime("%A")
        current_time = datetime.now().time()
        days_slots = list(filter(lambda s: s.weekday == this_weekday, self.slots))  # Get today's slots
        eligible_slots = list(filter(lambda s: s.start_time < current_time, days_slots))  # Filter out future slots
        if len(eligible_slots) == 0:
            logging.warning("Could not find slot for this time")
        else:
            self.set_current_slot(max(eligible_slots, key=lambda s: s.start_time))

    def calculate_daily_events(self):
        """ Get events that will occur today (to avoid sorting through all events every tick) """
        today = datetime.now()
        # Add a couple hours buffer either way, it wont hurt and it will stop unexpected dst shenanigans
        day_start = datetime(year=today.year, month=today.month, day=today.day) - timedelta(2)
        day_end = datetime(year=today.year, month=today.month, day=today.day, hour=23) + timedelta(3)
        self.daily_events = [e for e in self.events
                        if (e.event_start < day_start > e.event_end)  # Starts before the day but ends during/after day
                        or (day_start < e.event_start < day_end)]  # Starts during the day
        self.daily_events_date = today.date()

    def calculate_current_events(self):
        self.active_events = [e for e in self.daily_events if e.event_start < datetime.now() < e.event_end]
        if len(self.active_events) > 0:
            self.event_active = True
        else:
            self.event_active = False

    def update_assets_from_db(self):
        """ Load the slots from the database into the scheduler """
        self.last_update_db_mtime = get_db_mtime()
        session = Session()
        new_slots = session.query(ScheduleSlot).all()
        new_events = session.query(Event).all()
        session.close()
        if new_slots == self.slots and new_events == self.events:
            # If nothing changed, do nothing
            return
        self.slots = new_slots
        self.sort_slots()
        self.calculate_current_slot()
        for e in new_events:
            if e.event_end < datetime.now():
                new_events.remove(e)
        self.events = new_events
        logging.debug("New assets loaded into SlotHandler")


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


def build_schedule_slot_uri(schedule_slot: ScheduleSlot, event=None) -> str:
    hostname = f"{settings['local_address']}"
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
    if event:
        url_parameters["event_text"] = event.display_text if event.display_text else ""
        url_parameters["event_image_uuid"] = event.foreground_image_uuid

    url_parameters = urllib.parse.urlencode(url_parameters)
    uri = hostname + "/kenban?" + url_parameters
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


def display_loop(handler: SlotHandler):
    global last_slot
    if handler.current_slot is None:
        logging.info('Playlist is empty. Sleeping for %s seconds', EMPTY_PL_DELAY)
        view_image(LOAD_SCREEN)
        sleep(EMPTY_PL_DELAY)
    else:
        logging.debug(f"Current schedule slot start time: {handler.current_slot.start_time}")
        event = None
        if handler.event_active:
            event = handler.active_events[0]  # Just get the first event for now, maybe change this later
        uri = build_schedule_slot_uri(handler.current_slot, event)
        if last_slot != handler.current_slot:
            view_webpage(uri)
            last_slot = handler.current_slot
        refresh_duration = int(settings['default_duration'])
        logging.debug(f'Current slot: {handler.current_slot} Sleeping for {refresh_duration}')
        sleep(refresh_duration)

    if get_db_mtime() > handler.last_update_db_mtime:
        handler.update_assets_from_db()
    handler.tick()
    sleep(SCREEN_TICK_DELAY)


def setup():
    global HOME, browser_bus
    HOME = getenv('HOME', '/home/pi')

    signal(SIGUSR1, sigusr1)
    signal(SIGALRM, sigalrm)

    load_settings()

    load_browser()
    bus = pydbus.SessionBus()
    browser_bus = bus.get('screenly.webview', '/Screenly')


def show_hotspot_page():
    ssid = r.get("ssid").decode("utf-8")
    ssid_password = r.get("ssid-password").decode("utf-8")
    logging.info("Displaying hotspot page")
    logging.info(f"SSID = {ssid}")
    logging.info(f"SSID Password = {ssid_password}")
    url = f'http://{LISTEN}/hotspot?ssid={ssid}&ssid_password={ssid_password}'
    wait_for_server(retries=5)
    view_webpage(url)

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
    for _ in range(0, retries):
        try:
            wifi_status = r.get("wifi-status")
            if wifi_status:
                return int(wifi_status)
        except TypeError:
            sleep(wt)
    logging.error("Failed to wait for redis to start")


def device_pair():
    logging.info("Starting pairing")
    while True:
        device_code, verification_uri = register_new_client()
        if device_code is None:
            logging.error("Failed to register new client with server")
            view_webpage(f"http://{LISTEN}:{PORT}/connect-error?error=No response when trying to register new device")
            sleep(10)
            continue
        else:
            url = 'http://{0}:{1}/pair?user_code={2}&verification_uri={3}' \
                .format(LISTEN, PORT, device_code, verification_uri)
            view_webpage(url)
            auth_success = poll_for_authentication(device_code=device_code)
            if auth_success:
                logging.info("Device paired successfully")
                return
            else:
                logging.error("Authentication polling failed")
                view_webpage(f"http://{LISTEN}:{PORT}/connect-error")
                sleep(10)
                continue


def main():
    setup()

    wifi_status = get_wifi_status()
    if wifi_status:
        while wifi_status != WIFI_CONNECTED:
            if wifi_status == WIFI_CONNECTING:
                show_hotspot_page()
            elif wifi_status == WIFI_DISCONNECTED:
                logging.warning("wifi-status = Disconnected")
                sleep(1)
            else:
                logging.critical("Invalid wifi-status from redis: " + str(wifi_status))
            wifi_status = get_wifi_status()
    else:
        logging.warning("Failed to get wifi status. Continuing anyway")

    from settings import settings
    # Check to see if device is paired
    if settings["refresh_token"] in [None, "None", ""]:
        wait_for_server(retries=5)
        device_pair()
        view_image(NEW_SETUP_SCREEN)
        sleep(10)  # Wait for the server to setup the new screen before continuing
        sync.full_sync()
        confirm_setup_completion()
    else:
        logging.info(f"Device already paired")
        view_image(LOAD_SCREEN)

    handler = SlotHandler()

    logging.debug('Entering infinite loop.')
    while True:
        if loop_is_stopped:
            sleep(0.1)
            continue

        display_loop(handler)
        sleep(0.1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Viewer crashed.")
        raise
