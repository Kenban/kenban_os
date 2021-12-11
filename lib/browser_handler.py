import logging
from os import getenv
from time import sleep

import pydbus
import sh

from lib.utils import string_to_bool, connect_to_redis


class BrowserHandler(object):
    def __init__(self):
        self.browser = None
        self.load_browser()
        self._bus = pydbus.SessionBus()
        self._browser_bus = self._bus.get('screenly.webview', '/Screenly')
        self.current_browser_url = None

    def load_browser(self):
        logging.info('Loading browser...')

        self.browser = sh.Command('ScreenlyWebview')(_bg=True, _err_to_out=True)
        while 'Screenly service start' not in str(self.browser.process.stdout):
            sleep(1)

    def view_webpage(self, uri: str):
        r = connect_to_redis()
        if self.browser is None or not self.browser.process.alive:
            self.load_browser()
        if self.current_browser_url != uri:
            self._browser_bus.loadPage(uri)
            self.current_browser_url = uri
            logging.debug('Current url is {0}'.format(self.current_browser_url))
        elif r.exists("refresh-browser"):
            logging.info('Browser refresh forced')
            r.delete("refresh-browser")
            self._browser_bus.loadPage(uri)
            self.current_browser_url = uri
            logging.debug('Current url is {0}'.format(self.current_browser_url))

    def view_image(self, uri):
        if self.browser is None or not self.browser.process.alive:
            self.load_browser()
        if self.current_browser_url is not uri:
            self._browser_bus.loadImage(uri)
            self.current_browser_url = uri
        logging.debug('Current url is {0}'.format(self.current_browser_url))

        if string_to_bool(getenv('WEBVIEW_DEBUG', '0')):
            logging.info(self.browser.process.stdout)
