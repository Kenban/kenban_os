import os
import json
import logging
from datetime import datetime, time

import requests
from requests.exceptions import ConnectionError

from authentication import get_auth_header
from lib.models import Session, ScheduleSlot, Event
from settings import settings


def full_sync():
    sync_images()
    sync_templates()
    sync_schedule_slots()
    sync_events()
    settings["last_update"] = get_server_last_update_time()  # May save error message from the server. This is ok
    settings.save()


def sync_schedule_slots():
    """Get all of the user's schedule slots from the Kenban server and save them to local database"""
    url = settings['server_address'] + settings['schedule_url'] + settings["device_uuid"]
    headers = get_auth_header()
    logging.debug(f"Getting schedule from {url}")
    try:
        response = requests.get(url=url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        logging.warning("HTTP Error while requesting schedule:" + str(error))
        return None
    except ConnectionError:
        logging.warning("Could not connect to authorisation server at {0}".format(url))
        return None
    schedule_slots = json.loads(response.content)
    with Session() as session:
        for slot in schedule_slots:
            db_slot = session.query(ScheduleSlot).filter_by(uuid=slot["uuid"]).first()
            if not db_slot:
                db_slot = ScheduleSlot()
                session.add(db_slot)
            db_slot.uuid = slot["uuid"]
            db_slot.template_uuid = slot["template_uuid"]
            db_slot.foreground_image_uuid = slot["foreground_image_uuid"]
            db_slot.display_text = slot["display_text"]
            db_slot.time_format = slot["time_format"]
            db_slot.start_time = time_parser(slot["start_time"])
            db_slot.weekday = slot["weekday"]

            session.commit()


def sync_events():
    url = settings['server_address'] + settings['event_url'] + settings["device_uuid"]
    headers = get_auth_header()
    try:
        response = requests.get(url=url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        logging.warning("HTTP Error while requesting events:" + str(error))
        return None
    except ConnectionError:
        logging.warning("Could not connect to authorisation server at {0}".format(url))
        return None
    try:
        events = json.loads(response.content)
    except ValueError as e:
        logging.error(e)
        return None
    with Session() as session:
        for event in events:
            db_event = session.query(Event).filter_by(uuid=event["uuid"]).first()
            if not db_event:
                db_event = Event()
                session.add(db_event)
            db_event.uuid = event["uuid"]
            db_event.foreground_image_uuid = event["foreground_image_uuid"]
            db_event.display_text = event["display_text"]
            db_event.event_start = event["event_start"]
            db_event.event_end = event["event_end"]
            db_event.override = event["override"]
            session.commit()


def sync_images(overwrite=False):
    logging.debug("Syncing images")
    url = settings['server_address'] + settings['image_url']
    headers = get_auth_header()
    try:
        response = requests.get(url=url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        logging.warning("HTTP Error while requesting images:" + str(error))
        return None
    except ConnectionError:
        logging.warning("Could not connect to authorisation server at {0}".format(url))
        return None
    images = json.loads(response.content)
    if not os.path.exists(settings["images_folder"]):
        os.makedirs(settings["images_folder"])
    existing_file_uuids = os.listdir(settings["images_folder"])
    logging.debug("Existing images: " + str(existing_file_uuids))
    for image in images:
        if image['uuid'] in existing_file_uuids and not overwrite:
            logging.debug("Already got image " + image['uuid'])
            continue
        img_data = requests.get(image["src"]).content
        fp = settings["images_folder"] + image["uuid"]
        with open(fp, 'wb') as output_file:
            output_file.write(img_data)
            logging.info("Saving Image " + image["uuid"])


def sync_templates(overwrite=False):
    logging.debug("Syncing templates")
    url = settings['server_address'] + settings['template_url']
    headers = get_auth_header()
    try:
        response = requests.get(url=url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        logging.warning("HTTP Error while requesting templates:" + str(error))
        return None
    except ConnectionError:
        logging.warning("Could not connect to authorisation server at {0}".format(url))
        return None
    template_uuids = json.loads(response.content)
    if not os.path.exists(settings["templates_folder"]):
        os.makedirs(settings["templates_folder"])
    existing_template_uuids = os.listdir(settings["templates_folder"])
    logging.debug("Existing templates: " + str(existing_template_uuids))
    for template_uuid in template_uuids:
        if template_uuid in existing_template_uuids and not overwrite:
            logging.debug("Already got template " + template_uuid)
            continue
        url = settings["server_address"] + settings["template_url"] + template_uuid
        template = requests.get(url).content
        fp = settings["templates_folder"] + template_uuid
        with open(fp, 'wb') as output_file:
            output_file.write(template)
            logging.info("Saved template " + template_uuid)


def get_server_last_update_time():
    """ Gets the last time the user edited the screen schedule on the Kenban server."""
    logging.debug("Checking for update")
    device_uuid = str(settings['device_uuid'])
    url = settings['server_address'] + settings['update_url'] + "/" + device_uuid
    try:
        headers = get_auth_header()
        response = requests.get(url=url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        logging.warning("HTTP Error while requesting update time:" + str(error))
        return None
    except ConnectionError:
        logging.warning("Could not connect to authorisation server at {0}".format(url))
        return None
    server_update_time = json.loads(response.content)
    return server_update_time


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
