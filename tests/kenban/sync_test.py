from sync import full_sync
from schedule import init_kenban

import logging
logging.getLogger().setLevel(logging.DEBUG)

init_kenban()
full_sync()
