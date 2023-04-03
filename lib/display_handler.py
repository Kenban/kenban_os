import logging.config
from datetime import datetime, timedelta
from time import sleep

import humanize
from PyQt5.QtCore import QThread, pyqtSignal
from jinja2 import Environment, FileSystemLoader, select_autoescape

from lib.authentication import register_new_client, poll_for_authentication, get_auth_header
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

    def show_default_template(self, html):
        # noinspection PyUnresolvedReferences
        self.default_template.emit(html)

    def show_user_template(self, html):
        # noinspection PyUnresolvedReferences
        self.user_template.emit(html)

    def display_loop(self):
        r = connect_to_redis()
        if self.scheduler.current_slot is None:
            logger.info('Playlist is empty. Sleeping for %s seconds', EMPTY_PL_DELAY)
            html = default_templates_env.get_template("loading.html").render()
            self.show_default_template(html)
            sleep(EMPTY_PL_DELAY)
        else:
            if self.scheduler.event_active:
                events = self.scheduler.active_events
            else:
                events = []
            if self.scheduler.refresh_needed or r.exists("refresh-browser"):
                html = self.render_display_html(self.scheduler.current_slot, events)
                self.show_user_template(html)
                self.scheduler.refresh_needed = False
                r.delete("refresh-browser")
            banner_message = self.create_banner_message()
            r.publish("banner_message", banner_message)
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
            new_html = default_templates_env.get_template("hotspot.html"). \
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
                auth_success = poll_for_authentication(device_code=device_code)
                if auth_success:
                    logger.info("NoticeHome paired successfully")
                    return
                else:
                    logger.error("Authentication polling failed")
                    self.show_error_page("Network error. Please try restarting your NoticeHome. If this persists, "
                                         "contact Kenban support. ")
                    sleep(10)
                    continue

    def show_error_page(self, error_message):
        html = default_templates_env.get_template("error.html").render(message=error_message)
        self.show_default_template(html)

    def run(self):
        # noinspection PyBroadException
        try:
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
                    error_text = "Network error. Please try restarting your NoticeHome. If this persists, contact" \
                                 " Kenban support."
                    self.show_error_page(error_text)

            if settings["refresh_token"] in [None, "None", ""]:
                r = connect_to_redis()
                r.set("new-setup", 1, ex=3600)
                self.device_pair()
                html = default_templates_env.get_template("new-setup-screen.html").render()
                self.show_default_template(html)
                wait_for_initial_sync()
                self.confirm_setup_completion()
            else:
                logger.info(f"Device already paired")

            logger.debug('Entering infinite loop.')
            r.set("rebooted", 1, ex=15)
            while True:
                self.display_loop()
        except:
            logger.exception("Error in display handler")
            error_text = "Error. Please try restarting your NoticeHome. If this persists, contact Kenban support."
            self.show_error_page(error_text)

    def render_display_html(self, schedule_slot: ScheduleSlot, events) -> str:
        if not schedule_slot:
            error_message = "Error. Please try restarting your NoticeHome. If this persists, contact Kenban support."
            html = default_templates_env.get_template("error.html").render(message=error_message)
            logger.warning("build_schedule_slot_uri called with no active slot")
            return html

        # Add new setup message
        r = connect_to_redis()
        if schedule_slot.display_text in [None, ""] and r.exists("new-setup"):
            schedule_slot.display_text = "Customise this screen by visiting kenban.co.uk/schedule"
        if not schedule_slot.display_text:
            schedule_slot.display_text = ""

        html = user_templates_env.get_template(schedule_slot.template_uuid).render(
            slot=schedule_slot,
            events=events)
        return html

    def confirm_setup_completion(self):
        url = settings['server_address'] + settings['setup_complete'] + "/" + settings["device_uuid"]
        kenban_server_request(url=url, method='POST', data={"complete": True}, headers=get_auth_header())

    def create_banner_message(self):
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
                return f"Screen name = {settings['screen_name']}"
            else:
                return ""
        else:
            return ""
