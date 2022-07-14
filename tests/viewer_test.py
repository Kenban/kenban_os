import logging
import sys

from PyQt6.QtWidgets import QApplication

from lib.utils import connect_to_redis
from viewer import WebEngineView

r = connect_to_redis()
r.setbit("internet-connected", offset=0, value=1)
r.setbit("websocket-connected", offset=0, value=1)

app = QApplication(sys.argv)

screen = app.primaryScreen()
logging.debug('Screen: %s' % screen.name())
size = screen.size()
logging.debug('Size: %d x %d' % (size.width(), size.height()))
rect = screen.availableGeometry()
logging.debug('Available: %d x %d' % (rect.width(), rect.height()))

window = WebEngineView()
sys.exit(app.exec())