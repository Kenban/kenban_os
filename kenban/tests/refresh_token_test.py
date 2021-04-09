import requests

from kenban.settings_kenban import settings as k_settings
from kenban.authentication import refresh_access_token, get_access_token
import logging
logging.getLogger().setLevel(logging.DEBUG)
access_token = refresh_access_token()

headers = {"Authorization": "Bearer " + access_token}
url = k_settings['server_address'] + "/api/v1/auth/verify"
response = requests.get(url=url, headers=headers)
assert response.status_code == 200

access_token = get_access_token()
print(access_token)
pass