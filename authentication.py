import datetime
import json
import logging
import uuid
from json import JSONDecodeError
from os import getenv
from time import mktime
from time import sleep


import jwt
import requests
from requests.exceptions import ConnectionError

from lib.utils import kenban_server_request
from settings import settings

PORT = int(getenv('PORT', 8080))
LISTEN = getenv('LISTEN', '127.0.0.1')


def get_access_token():
    access_token = settings["access_token"]
    decoded_access_token = jwt.decode(access_token, algorithm="HS256", verify=False)
    current_timestamp = mktime(datetime.datetime.now().timetuple())
    if current_timestamp > decoded_access_token["exp"]:
        access_token = refresh_access_token()
    return access_token


def get_auth_header():
    access_token = get_access_token()
    header = {"Authorization": "Bearer " + access_token}
    return header


def register_new_client():
    """ Sends the client uuid to the server and receives the device code/verification uri in response"""
    url = settings['server_address'] + settings['device_register_uri']
    device_uuid = str(settings['device_uuid'])
    if device_uuid in [None, "", "None"]:
        device_uuid = uuid.uuid4().hex
        settings['device_uuid'] = device_uuid
        settings.save()
    try:
        data = json.dumps({u"uuid": device_uuid})
        response = requests.post(url=url,
                                 data=data,
                                 headers={'content-type': 'application/json'})
    except ConnectionError:
        logging.warning("Could not connect to authorisation server at {0}".format(url))
        return None, None
    except ValueError:
        logging.warning("Failed to decode server response during authorisation polling")
        return None, None
    try:
        response_body = json.loads(response.content)
    except JSONDecodeError:
        logging.warning(f"Failed to decode JSON response during authorisation polling. Response: {response}")
        return None, None
    return response_body["device_code"], response_body["verification_uri"]


def poll_for_authentication(device_code):
    """ To be called after getting device info, when this device does not yet have an access token or refresh token.
    Contacts the authentication server to get a user_code, which is then displayed to the user.
    Polls the authentication server until the user authenticates with the user_code"""
    logging.info("Entering loop to authorise device...")
    errors = 0
    while True:
        logging.info("Polling server for authorisation...")
        url = settings['server_address'] + settings['device_auth_uri']
        data = json.dumps({"device_code": device_code})
        try:
            response = requests.post(url=url, data=data)
        except ConnectionError:
            logging.warning("Could not connect to authorisation server at {0}".format(url))
            sleep(5)
            continue
        if response.status_code == 400:
            # This is normal in the device pair flow
            message = json.loads(response.content)["detail"]
            if "authorisation_pending" in message["error"]:
                sleep(5)
                continue
        elif response.status_code == 200:
            try:
                response_body = json.loads(response.content)
            except JSONDecodeError:
                logging.error("Failed to decode JSON response after apparently successful device pairing")
                return False
            settings["refresh_token"] = response_body["refresh_token"]
            settings["access_token"] = response_body["access_token"]
            settings["screen_name"] = response_body["screen_name"]
            settings.save()
            logging.info("Access tokens received from server")
            return True
        else:
            errors += 1
            if errors > 10:
                logging.error("Restarting pairing cycle")
                return False
            logging.error("Invalid server response during pairing.")
            logging.debug(response)
            sleep(10)
            continue


def refresh_access_token():
    """ Use a refresh token to gain a new access token from the server """
    logging.info("Getting new access token from server")
    refresh_token = settings["refresh_token"]
    if not refresh_token:
        logging.error("No refresh token")
        return None
    data = json.dumps({"refresh_token": settings["refresh_token"]})
    url = settings['server_address'] + settings["refresh_access_token_url"]
    response = kenban_server_request(url=url, method='POST', data=data)
    access_token = response["access_token"]
    if not access_token:
        logging.error("Failed to get access token from server response")
        return None
    settings["access_token"] = access_token
    settings.save()
    return access_token
