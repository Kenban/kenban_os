from lib.sync import full_sync

import logging.config

logging.config.fileConfig(fname='logging.ini', disable_existing_loggers=True)

full_sync()
