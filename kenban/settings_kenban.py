import configparser
import logging
import uuid
from collections import UserDict
import os

CONFIG_DIR = '.kenban'

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
    }
}


class KenbanSettings(UserDict):
    def __init__(self, *args, **kwargs):
        UserDict.__init__(self, *args, **kwargs)
        self.home = os.getenv('HOME')
        self.conf_file = self.get_configfile()
        if not os.path.isfile(self.conf_file):
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
        except configparser.Error as e:
            logging.debug("Could not parse setting '%s.%s': %s. Using default value: '%s'." % (
                section, field, str(e), default))

    def _set(self, config, section, field, default):
        if isinstance(default, bool):
            config.set(section, field, self.get(field, default) and 'on' or 'off')
        else:
            config.set(section, field, str(self.get(field, default)))

    def load(self):
        """Loads the latest settings from kenban.conf into memory."""
        logging.debug('Reading config-file...')
        config = configparser.ConfigParser()
        config.read(self.conf_file)

        for section, defaults in list(DEFAULTS.items()):
            for field, default in list(defaults.items()):
                self._get(config, section, field, default)

    def use_defaults(self):
        for defaults in DEFAULTS.items():
            for field, default in list(defaults[1].items()):
                if field == 'device_uuid':
                    self[field] = uuid.uuid1().hex
                else:
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

    def get_configfile(self):
        return os.path.join(self.home, CONFIG_DIR, "kenban.conf")


settings = KenbanSettings()
