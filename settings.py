#!/usr/bin/env python
# -*- coding: utf-8 -*-
import configparser
import hashlib
import logging
import os
from collections import UserDict
from os import path, getenv

CONFIG_DIR = '.kenban'
CONFIG_FILE = 'kenban.conf'

DEFAULTS = {
    'main': {
        'server_address': 'https://kenban.co.uk',
        'local_address': 'http://kb-os-nginx',
        'websocket_updates_address': 'ws://kenban.co.uk/api/v1/screen/subscribe/',
        'device_uuid': None,
        'last_update': None,
        'access_token': None,
        'refresh_token': None
    },
    'api': {
        'device_register_uri': '/api/v1/device_pairing/new',
        'device_auth_uri': '/api/v1/device_pairing/authorise',
        'refresh_access_token_url': '/api/v1/auth/access-token-refresh',
        'update_url': '/api/v1/screen/last_update',
        'image_url': '/api/v1/image/',
        'template_url': '/api/v1/template/',
        'schedule_url': '/api/v1/schedule/screen/',
        'event_url': '/api/v1/event/screen/',
    },
    'folders': {
        'images_folder': '/data/kenban_assets/kenban_images/',
        'templates_folder': '/data/kenban_assets/kenban_templates/',
    },
    'viewer': {
        'audio_output': 'hdmi',
        'debug_logging': False,
        'default_duration': '10',
        'default_streaming_duration': '300',
        'player_name': '',
        'resolution': '1920x1080',
        'show_splash': False,
        'shuffle_playlist': False,
        'verify_ssl': True,
        'usb_assets_key': '',
        'default_assets': False
    },
    'screenly': {
        'analytics_opt_out': False,
        'assetdir': 'kenban_assets',
        'database': os.path.join(CONFIG_DIR, 'kenban.db'),
        'date_format': 'mm/dd/yyyy',
        'use_24_hour_clock': False,
        'use_ssl': False,
        'auth_backend': '',
        'websocket_port': '9999'
    }
}


CONFIGURABLE_SETTINGS = DEFAULTS['viewer'].copy()
CONFIGURABLE_SETTINGS['use_24_hour_clock'] = DEFAULTS['screenly']['use_24_hour_clock']
CONFIGURABLE_SETTINGS['date_format'] = DEFAULTS['screenly']['date_format']

PORT = int(getenv('PORT', 8080))
LISTEN = getenv('LISTEN', '127.0.0.1')

# Initiate logging
logging.basicConfig(level=logging.INFO,
                    format='%(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')

# Silence urllib info messages ('Starting new HTTP connection')
# that are triggered by the remote url availability check in view_web
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)

logging.debug('Starting viewer.py')


class KenbanSettings(UserDict):
    """Kenban OS's Settings."""

    def __init__(self, *args, **kwargs):
        UserDict.__init__(self, *args, **kwargs)
        self.home = getenv('HOME')
        self.conf_file = self.get_configfile()

        if not path.isfile(self.conf_file):
            logging.error('Config-file %s missing. Using defaults.', self.conf_file)
            self.use_defaults()
            self.save()
        else:
            self.load()

    def _get(self, config, section, field, default):
        try:
            if isinstance(default, bool):
                self[field] = config.getboolean(section, field)
            elif isinstance(default, int):
                self[field] = config.getint(section, field)
            else:
                self[field] = config.get(section, field)
                if field == 'password' and self[field] != '' and len(self[field]) != 64:   # likely not a hashed password.
                    self[field] = hashlib.sha256(self[field]).hexdigest()   # hash the original password.
        except configparser.Error as e:
            logging.debug("Could not parse setting '%s.%s': %s. Using default value: '%s'." % (section, field, str(e), default))
            self[field] = default
        if field in ['database', 'assetdir']:
            self[field] = str(path.join(self.home, self[field]))

    def _set(self, config, section, field, default):
        if isinstance(default, bool):
            config.set(section, field, self.get(field, default) and 'on' or 'off')
        else:
            config.set(section, field, str(self.get(field, default)))

    def load(self):
        """Loads the latest settings from kenban.conf into memory."""
        logging.debug('Reading config-file...')
        config = configparser.ConfigParser(allow_no_value=True)
        config.read(self.conf_file)

        for section, defaults in DEFAULTS.items():
            for field, default in list(defaults.items()):
                self._get(config, section, field, default)

    def use_defaults(self):
        for defaults in DEFAULTS.items():
            for field, default in list(defaults[1].items()):
                self[field] = default

    def save(self):
        # Write new settings to disk.
        config = configparser.ConfigParser()
        for section, defaults in DEFAULTS.items():
            config.add_section(section)
            for field, default in list(defaults.items()):
                self._set(config, section, field, default)
        with open(self.conf_file, "w") as f:
            config.write(f)
        self.load()

    def get_configdir(self):
        return path.join(self.home, CONFIG_DIR)

    def get_configfile(self):
        return path.join(self.home, CONFIG_DIR, CONFIG_FILE)


settings = KenbanSettings()

