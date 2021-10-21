from time import sleep

from settings import LISTEN, PORT
from authentication import register_new_client, poll_for_authentication
import logging
logging.getLogger().setLevel(logging.DEBUG)


def pair_device_to_user():

    try:
        device_code, verification_uri = register_new_client()
    except:
        print("Failed to contact server while attempting to pair")
        return None
    if device_code:
        # Display the user_code and verification uri
        url = 'http://{0}:{1}/pair?user_code={2}&verification_uri={3}' \
            .format(LISTEN, PORT, device_code, verification_uri)
        print("device code = ", device_code)
        # Ping the server until the device pairing is complete
        poll_for_authentication(device_code=device_code)
    else:
        # If the connection to the server fails, show the connection failed screen and pause 15 seconds before continuing
        url = 'http://{0}:{1}/connection_failed' \
            .format(LISTEN, PORT)
        #browser_url(url=url)
        sleep(15)


if __name__ == "__main__":
    pair_device_to_user()
