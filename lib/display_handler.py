import logging.config
import os
from datetime import datetime, timedelta
from time import sleep

import humanize

if os.environ.get("DEV") == "True":
    from PyQt6.QtCore import QThread, pyqtSignal
else:
    from PyQt5.QtCore import QThread, pyqtSignal

from lib.authentication import register_new_client, poll_for_authentication, get_auth_header
from jinja2 import Environment, FileSystemLoader, select_autoescape
from lib.models import ScheduleSlot
from lib.scheduler import Scheduler
from lib.utils import connect_to_redis, get_db_mtime, wait_for_wifi_manager, kenban_server_request, \
    wait_for_initial_sync
from settings import settings

EMPTY_PL_DELAY = 5  # secs
SCREEN_TICK_DELAY = 0.2  # secs

logging.config.fileConfig(fname='logging.ini', disable_existing_loggers=True)
logger = logging.getLogger("viewer")

default_templates_env = Environment(
    loader=FileSystemLoader(settings["default_templates_folder"]),
    autoescape=select_autoescape()
)

user_templates_env = Environment(
    loader=FileSystemLoader(settings["templates_folder"]),
    autoescape=select_autoescape()
)


# noinspection PyMethodMayBeStatic
class DisplayHandler(QThread):
    default_template = pyqtSignal(str)
    user_template = pyqtSignal(str)

    def __init__(self):
        self.scheduler = Scheduler()
        self.current_banner_message = ""
        super(DisplayHandler, self).__init__()

    # def __del__(self):
    #     self.wait()

    def show_default_template(self, html):
        # noinspection PyUnresolvedReferences
        self.default_template.emit(html)

    def show_user_template(self, html):
        # noinspection PyUnresolvedReferences
        self.user_template.emit(html)

    def display_loop(self):
        if self.scheduler.current_slot is None:
            logger.info('Playlist is empty. Sleeping for %s seconds', EMPTY_PL_DELAY)
            html = default_templates_env.get_template("loading.html").render()
            self.show_default_template(html)
            sleep(EMPTY_PL_DELAY)
        else:
            event = None
            if self.scheduler.event_active:
                event = self.scheduler.active_events[0]  # Just get the first event for now, maybe change this later
            if self.scheduler.refresh_needed:
                html = self.render_display_html(self.scheduler.current_slot, event)
                self.show_user_template(html)
                self.scheduler.refresh_needed = False
            banner_message = self.create_banner_message()
            if banner_message != self.current_banner_message:
                self.scheduler.refresh_needed = True
                self.current_banner_message = banner_message

        if get_db_mtime() > self.scheduler.last_update_db_mtime:
            self.scheduler.update_assets_from_db()
        self.scheduler.tick()
        sleep(SCREEN_TICK_DELAY)

    def show_hotspot_page(self):
        r = connect_to_redis()
        # Set a flag, so we can display "connection successful" on the next screen
        r.set("hotspot-connected-this-session", value="True", ex=timedelta(seconds=30))
        ssid = r.get("ssid").decode("utf-8")
        ssid_password = r.get("ssid-password").decode("utf-8")
        logger.info("Displaying hotspot page")
        logger.info(f"SSID = {ssid}")
        logger.info(f"SSID Password = {ssid_password}")
        current_html = ""
        status = ""
        # Enter a loop to update the display according to wifi-connect progress
        while status != "success":
            status = r.get("wifi-connect-status").decode('utf-8')
            if status == "user-on-portal":
                show_hotspot_connection_instructions = False
                show_home_wifi_password_instructions = True
                show_connecting_spinner = False
                show_error_message = False
            elif status == "connecting":
                show_hotspot_connection_instructions = False
                show_home_wifi_password_instructions = False
                show_connecting_spinner = True
                show_error_message = False
            elif status == "user-error":
                show_hotspot_connection_instructions = True
                show_home_wifi_password_instructions = False
                show_connecting_spinner = False
                show_error_message = True
            else:
                show_hotspot_connection_instructions = True
                show_home_wifi_password_instructions = False
                show_connecting_spinner = False
                show_error_message = False
            new_html = default_templates_env.get_template("hotspot.html").\
                render(ssid=ssid,
                       ssid_password=ssid_password,
                       show_hotspot_connection_instructions=show_hotspot_connection_instructions,
                       connecting=show_connecting_spinner,
                       error=show_error_message,
                       show_home_wifi_password_instructions=show_home_wifi_password_instructions)
            if new_html != current_html:
                current_html = new_html
                self.show_default_template(current_html)
            sleep(0.2)

    def device_pair(self):
        logger.info("Starting pairing")
        while True:
            device_code, verification_uri = register_new_client()
            if device_code is None:
                logger.error("Failed to register new client with server")
                error_text = "Network error. Please try restarting your device. If this persists, contact support."
                self.show_error_page(error_text)
                sleep(10)
                continue
            else:
                r = connect_to_redis()
                show_connection_success = r.exists("hotspot-connected-this-session")
                html = default_templates_env.get_template("pair.html").render(
                    pair_code=device_code,
                    verification_uri=verification_uri,
                    show_connection_success=show_connection_success)
                self.show_default_template(html=html)
                try:
                    auth_success = poll_for_authentication(device_code=device_code)
                except Exception:
                    logger.exception(msg="Authentication polling failed")
                    auth_success = False
                if auth_success:
                    logger.info("NoticeHome paired successfully")
                    return
                else:
                    logger.error("Authentication polling failed")
                    self.show_error_page("Network error. Please try restarting your NoticeHome. If this persists, "
                                         "contact support. ")
                    sleep(10)
                    continue

    def show_error_page(self, error_message):
        html = default_templates_env.get_template("error.html").render(message=error_message)
        self.show_default_template(html)

    def run(self):
        # todo handle first start up with an internet connection but not a connection to the server
        from settings import settings
        settings.load()

        r = connect_to_redis()
        wm = wait_for_wifi_manager()

        # Check to see if we have internet and if Wi-Fi manager is starting a hotspot
        if wm:
            while not r.getbit("internet-connected", 0):
                if r.getbit("wifi-manager-connecting", 0):
                    self.show_hotspot_page()
                else:
                    sleep(0.1)
        else:  # Wi-Fi manager has failed to start
            if settings["refresh_token"] in [None, "None", ""]:
                # If device is paired, continue anyway
                r = connect_to_redis()
                logger.warning("Continuing without wifi setup")
            else:
                # If device isn't paired, we can't continue
                error_text = "Network error. Please try restarting your NoticeHome. If this persists, contact support."
                self.show_error_page(error_text)

        if settings["refresh_token"] in [None, "None", ""]:
            r = connect_to_redis()
            r.set("new-setup", 1, ex=3600)
            self.device_pair()
            self.show_default_template("new-setup-screen.html")
            wait_for_initial_sync()
            self.confirm_setup_completion()
        else:
            logger.info(f"Device already paired")

        logger.debug('Entering infinite loop.')
        r.set("rebooted", 1, ex=15)
        while True:
            self.display_loop()

    def render_display_html(self, schedule_slot: ScheduleSlot, event=None) -> str:
        # Add the info for the schedule slot
        if not schedule_slot:
            html = default_templates_env.get_template("splash-page.html").render()
            logger.warning("build_schedule_slot_uri called with no active slot")
            return html

        display_text = schedule_slot.display_text if schedule_slot.display_text else ""
        foreground_image_uuid = schedule_slot.foreground_image_uuid
        time_format = schedule_slot.time_format
        banner_message = self.create_banner_message()

        # Add new setup message
        r = connect_to_redis()
        if schedule_slot.display_text in [None, ""] and r.exists("new-setup"):
            display_text = "Customise this screen by visiting kenban.co.uk/schedule"

        if event:
            event_text = event.display_text if event.display_text else ""
            event_image_uuid = event.foreground_image_uuid
        else:
            event_text = None
            event_image_uuid = None
        html = user_templates_env.get_template(schedule_slot.template_uuid).render(
            display_text=display_text,
            foreground_image_uuid=foreground_image_uuid,
            time_format=time_format,
            event_text=event_text,
            event_image_uuid=event_image_uuid,
            banner_message=banner_message)
        return html

    def confirm_setup_completion(self):
        url = settings['server_address'] + settings['setup_complete'] + "/" + settings["device_uuid"]
        kenban_server_request(url=url, method='POST', data={"complete": True}, headers=get_auth_header())

    def create_banner_message(self):
        # todo if wifi manager doesnt start we dont see a banner
        """ Build banner message text for error messages, based on flags that have been set in redis """
        r = connect_to_redis()

        if not r.getbit("internet-connected", offset=0):
            if r.exists("last-connected"):
                last_connected = float(r.get("last-connected").decode('utf-8'))
                last_connected = datetime.fromtimestamp(last_connected)
                last_connected_text = humanize.naturaltime(last_connected)
                if "second" in last_connected_text:
                    last_connected_text = "less than a minute ago"
                return f"No internet connection found. " \
                       f"Last connected {last_connected_text}. " \
                       f"Restart device to connect to a new Wi-Fi Network"
            return "No internet connection found"

        elif not r.getbit("websocket-connected", offset=0):
            if r.exists("websocket-dc-timestamp"):
                last_ws_connected = float(r.get("websocket-dc-timestamp").decode('utf-8'))
                last_ws_connected = datetime.fromtimestamp(last_ws_connected)
                last_ws_connected_text = humanize.naturaltime(last_ws_connected)
                if "second" in last_ws_connected_text:
                    last_ws_connected_text = "less than a minute ago"
                return f"Unable to reach Kenban server. Last sync {last_ws_connected_text}"
            return f"Unable to reach Kenban server."
        elif r.exists("rebooted"):
            if settings["screen_name"] not in [None, "", "None"]:
                # todo I don't like this because it causes a refresh (and screen flashes) a few seconds after startup
                return f"Screen name = {settings['screen_name']}"
            else:
                return ""
        else:
            return ""
