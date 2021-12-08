import os
import logging
from datetime import timedelta
from random import randrange

import requests
from celery.schedules import crontab
from celery import Celery

from authentication import get_auth_header
from lib.db_helper import create_or_update_schedule_slot, create_or_update_event
from lib.models import Session
from lib.utils import kenban_server_request
from settings import settings


HOME = os.getenv('HOME', '/home/pi')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_TASK_RESULT_EXPIRES = timedelta(hours=6)

celery = Celery(
    "websocket",
    backend=CELERY_RESULT_BACKEND,
    broker=CELERY_BROKER_URL,
    result_expires=CELERY_TASK_RESULT_EXPIRES
)


@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # todo set full sync task up properly
    hour = randrange(0, 24)
    minute = randrange(0, 60)
    day = randrange(0, 7)
    sender.add_periodic_task(crontab(hour=hour, minute=minute, day_of_week=day), full_sync.s(), )


@celery.task
def full_sync():
    logging.info("Performing full sync with kenban server")
    sync_images()
    sync_templates()
    sync_schedule_slots()
    sync_events()
    settings["last_update"] = get_server_last_update_time()  # May save error message from the server. This is ok
    settings.save()


def sync_schedule_slots():
    """Get all of the user's schedule slots from the Kenban server and save them to local database"""
    url = settings['server_address'] + settings['schedule_url'] + settings["device_uuid"]
    schedule_slots = kenban_server_request(url=url, method='GET', headers=get_auth_header())
    if not schedule_slots:
        return None
    with Session() as session:
        for slot in schedule_slots:
            create_or_update_schedule_slot(session, slot)
        session.commit()


def sync_events():
    url = settings['server_address'] + settings['event_url'] + settings["device_uuid"]
    events = kenban_server_request(url=url, method='GET', headers=get_auth_header())
    if not events:
        return None
    with Session() as session:
        for event in events:
            create_or_update_event(session, event)
        session.commit()


def sync_images(overwrite=False):
    url = settings['server_address'] + settings['image_url']
    images = kenban_server_request(url=url, method='GET', headers=get_auth_header())
    if not images:
        return None
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
    url = settings['server_address'] + settings['template_url']
    template_uuids = kenban_server_request(url=url, method='GET', headers=get_auth_header())
    if not template_uuids:
        return None
    if not os.path.exists(settings["templates_folder"]):
        os.makedirs(settings["templates_folder"])
    existing_template_uuids = os.listdir(settings["templates_folder"])
    logging.debug("Existing templates: " + str(existing_template_uuids))
    for template_uuid in template_uuids:
        if template_uuid in existing_template_uuids and not overwrite:
            logging.debug("Already got template " + template_uuid)
            continue
        url = settings["server_address"] + settings["template_url"] + template_uuid
        template = kenban_server_request(url=url, method='GET', headers=get_auth_header(), decode_json=False)
        fp = settings["templates_folder"] + template_uuid
        with open(fp, 'wb') as output_file:
            output_file.write(template)
            logging.info("Saved template " + template_uuid)


def get_image(image_uuid):
    url = settings['server_address'] + settings['image_url'] + image_uuid
    image = kenban_server_request(url=url, method='GET', headers=get_auth_header())
    if not image:
        return None
    if not os.path.exists(settings["images_folder"]):
        os.makedirs(settings["images_folder"])
    img_data = requests.get(image["src"]).content
    fp = settings["images_folder"] + image["uuid"]
    with open(fp, 'wb') as output_file:
        output_file.write(img_data)
        logging.info("Saving Image " + image["uuid"])


def get_server_last_update_time():
    """ Gets the last time the user edited the screen schedule on the Kenban server."""
    logging.debug("Checking for update")
    device_uuid = str(settings['device_uuid'])
    url = settings['server_address'] + settings['update_url'] + "/" + device_uuid
    server_update_time = kenban_server_request(url=url, method='GET', headers=get_auth_header())
    return server_update_time
