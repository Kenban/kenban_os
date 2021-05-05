import json
import logging
import os

import requests
from requests.exceptions import ConnectionError

import schedule
from kenban.authentication import get_auth_header
from settings_kenban import settings as k_settings


def get_server_last_update_time():
    """ Compares the last updated time with the server. Returns true if an update is needed"""
    logging.debug("Checking for update")
    try:
        device_uuid = str(k_settings['device_uuid']).decode('utf-8')
        url = k_settings['server_address'] + k_settings['update_url'] + "/" + device_uuid
        headers = get_auth_header()
        response = requests.get(url=url, headers=headers)
    except ConnectionError:
        logging.warning("Could not connect to authorisation server at {0}".format(url))
        return None
    server_update_time = json.loads(response.content)
    return server_update_time


def get_all_images(overwrite=False):
    logging.debug("Syncing images")
    try:
        url = k_settings['server_address'] + k_settings['image_url']
        headers = get_auth_header()
        response = requests.get(url=url, headers=headers)
    except ConnectionError:
        logging.warning("Could not connect to authorisation server at {0}".format(url))
        return None
    images = json.loads(response.content)
    if not os.path.exists(k_settings["images_folder"]):
        os.makedirs(k_settings["images_folder"])
    existing_file_uuids = os.listdir(k_settings["images_folder"])
    logging.debug("Existing images: " + str(existing_file_uuids))
    for image in images:
        if image['uuid'] in existing_file_uuids and not overwrite:
            logging.debug("Already got image " + image['uuid'])
            continue
        img_data = requests.get(image["src"]).content
        fp = k_settings["images_folder"] + image["uuid"]
        with open(fp, 'wb') as output_file:
            output_file.write(img_data)
            logging.info("Saving Image " + image["uuid"])


def get_all_templates(overwrite=False):
    #todo error check. A server error will save a file with the server error in it
    logging.debug("Syncing templates")
    try:
        url = k_settings['server_address'] + k_settings['template_url']
        headers = get_auth_header()
        response = requests.get(url=url, headers=headers)
    except ConnectionError:
        logging.warning("Could not connect to authorisation server at {0}".format(url))
        return None
    template_uuids = json.loads(response.content)
    if not os.path.exists(k_settings["templates_folder"]):
        os.makedirs(k_settings["templates_folder"])
    existing_template_uuids = os.listdir(k_settings["templates_folder"])
    logging.debug("Existing templates: " + str(existing_template_uuids))
    for template_uuid in template_uuids:
        if template_uuid in existing_template_uuids and not overwrite:
            logging.debug("Already got template " + template_uuid)
            continue
        url = k_settings["server_address"] + k_settings["template_url"] + template_uuid
        template = requests.get(url).content
        fp = k_settings["templates_folder"] + template_uuid
        with open(fp, 'wb') as output_file:
            output_file.write(template)
            logging.info("Saved template " + template_uuid)


def get_schedule():
    logging.debug("Getting schedule")
    try:
        url = k_settings['server_address'] + k_settings['schedule_url'] + k_settings["device_uuid"]
        headers = get_auth_header()
        response = requests.get(url=url, headers=headers)
    except ConnectionError:
        logging.warning("Could not connect to authorisation server at {0}".format(url))
        return None
    schedule_slots = json.loads(response.content)
    existing_slot_uuids = schedule.get_schedule_slot_uuids()
    for slot in schedule_slots:
        # If the slot already exists, update the table
        slot_exists = slot["uuid"] in existing_slot_uuids
        logging.debug("Saving slot " + slot["uuid"])
        schedule.save_schedule_slot(slot, update=slot_exists)


def get_all_events():
    try:
        url = k_settings['server_address'] + k_settings['event_url'] + k_settings["device_uuid"]
        headers = get_auth_header()
        response = requests.get(url=url, headers=headers)
    except ConnectionError:
        logging.warning("Could not connect to authorisation server at {0}".format(url))
        return None
    try:
        events = json.loads(response.content)
    except ValueError as e:
        logging.error(e)

    existing_event_uuids = schedule.get_event_uuids()
    for event in events:
        event_exists = event["uuid"] in existing_event_uuids
        logging.debug("Saving slot " + event["uuid"])
        schedule.save_event(event, update=event_exists)
