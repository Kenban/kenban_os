import requests

from settings import settings
from kenban.authentication import refresh_access_token, get_access_token
import logging
logging.getLogger().setLevel(logging.DEBUG)
access_token = refresh_access_token()

headers = {"Authorization": "Bearer " + access_token}
url = settings['server_address'] + "/api/v1/auth/verify"
response = requests.get(url=url, headers=headers)
assert response.status_code == 200

access_token = get_access_token()
print(access_token)
pass