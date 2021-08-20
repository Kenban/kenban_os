import json
import logging
import os
from datetime import timedelta

import requests
from celery import Celery
from requests.exceptions import ConnectionError

from kenban.schedule import get_event_uuids, get_schedule_slot_uuids, save_event, save_schedule_slot, build_assets_table
from kenban.authentication import get_auth_header
from settings import settings


CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_TASK_RESULT_EXPIRES = timedelta(hours=6)

celery = Celery(
    "kenban",
    backend=CELERY_RESULT_BACKEND,
    broker=CELERY_BROKER_URL,
    result_expires=CELERY_TASK_RESULT_EXPIRES
)


def full_sync():
    get_all_images()
    get_all_templates()
    get_schedule()
    get_all_events()
    build_assets_table()
    settings["last_update"] = get_server_last_update_time()  # May save error message from the server. This is ok
    settings.save()


def get_server_last_update_time():
    """ Compares the last updated time with the server. Returns true if an update is needed"""
    logging.debug("Checking for update")
    try:
        device_uuid = str(settings['device_uuid'])
        url = settings['server_address'] + settings['update_url'] + "/" + device_uuid
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


def get_all_images(overwrite=False):
    logging.debug("Syncing images")
    try:
        url = settings['server_address'] + settings['image_url']
        headers = get_auth_header()
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


def get_all_templates(overwrite=False):
    logging.debug("Syncing templates")
    try:
        url = settings['server_address'] + settings['template_url']
        headers = get_auth_header()
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


def get_schedule():
    logging.debug("Getting schedule")
    try:
        url = settings['server_address'] + settings['schedule_url'] + settings["device_uuid"]
        headers = get_auth_header()
        response = requests.get(url=url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        logging.warning("HTTP Error while requesting schedule:" + str(error))
    except ConnectionError:
        logging.warning("Could not connect to authorisation server at {0}".format(url))
        return None
    schedule_slots = json.loads(response.content)
    existing_slot_uuids = get_schedule_slot_uuids()
    for slot in schedule_slots:
        # If the slot already exists, update the table
        slot_exists = slot["uuid"] in existing_slot_uuids
        logging.debug("Saving slot " + slot["uuid"])
        save_schedule_slot(slot, update=slot_exists)


def get_all_events():
    try:
        url = settings['server_address'] + settings['event_url'] + settings["device_uuid"]
        headers = get_auth_header()
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

    existing_event_uuids = get_event_uuids()
    for event in events:
        event_exists = event["uuid"] in existing_event_uuids
        logging.debug("Saving slot " + event["uuid"])
        save_event(event, update=event_exists)


@celery.task()
def update_schedule(force=False):
    logging.debug("Checking for update")
    local_update_time = settings["last_update"]
    server_update_time = get_server_last_update_time()
    if local_update_time != server_update_time or force:
        get_all_images()
        get_all_templates()
        get_schedule()
        get_all_events()
        build_assets_table()

        settings["last_update"] = server_update_time  # May save an error message returned from the server. This is ok
        settings.save()


@celery.on_after_finalize.connect
def setup_periodic_kenban_tasks(sender, **kwargs):
    sender.add_periodic_task(10, update_schedule.s(), name='schedule_update')

