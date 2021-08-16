import datetime
import json
import logging
from os import getenv
from time import mktime
from time import sleep

import jwt
import requests
from requests.exceptions import ConnectionError

from kenban.settings_kenban import settings as k_settings

PORT = int(getenv('PORT', 8080))
LISTEN = getenv('LISTEN', '127.0.0.1')

def get_access_token():
    access_token = k_settings["access_token"]
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
    try:
        url = k_settings['server_address'] + k_settings['device_register_uri']
        device_uuid = str(k_settings['device_uuid'])
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
    response_body = json.loads(response.content)
    return response_body["device_code"], response_body["verification_uri"]


def poll_for_authentication(device_code):
    """ To be called after getting device info, when this device does not yet have an access token or refresh token.
    Contacts the authentication server to get a user_code, which is then displayed to the user.
    Polls the authentication server until the user authenticates with the user_code"""
    logging.info("Entering loop to authorise device...")
    while True:
        logging.info("Polling server for authorisation...")
        url = k_settings['server_address'] + k_settings['device_auth_uri']
        data = json.dumps({"device_code": device_code})
        try:
            response = requests.post(url=url, data=data)
        except ConnectionError:
            logging.warning("Could not connect to authorisation server at {0}".format(url))
            sleep(5)
            continue
        if response.status_code == 400:
            message = json.loads(response.content)["detail"]
            if "authorisation_pending" in message["error"]:
                sleep(5)
                continue
        elif response.status_code == 200:
            response_body = json.loads(response.content)
            k_settings["refresh_token"] = response_body["refresh_token"]
            k_settings["access_token"] = response_body["access_token"]
            k_settings.save()
            logging.info("Device paired.")
        logging.info("Initial token successfully received from server.")
        return True


def refresh_access_token():
    """ Use a refresh token to gain a new access token from the server """
    refresh_token = k_settings["refresh_token"]
    if not refresh_token:
        logging.error("No refresh token")
        return None
    data = json.dumps({"refresh_token": k_settings["refresh_token"]})
    url = k_settings['server_address'] + k_settings["refresh_access_token_url"]
    response = requests.post(url=url, data=data)
    access_token = json.loads(response.content)["access_token"]
    k_settings["access_token"] = access_token
    k_settings.save()
    return access_token
