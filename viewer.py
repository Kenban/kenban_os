import logging
import sys

from PyQt5.QtCore import QUrl, Qt
from PyQt5.QtGui import QCursor
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout

from lib.display_handler import DisplayHandler
from lib.models import Base, engine
from settings import settings

Base.metadata.create_all(engine)

app = QApplication(sys.argv)

logger = logging.getLogger("viewer")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
f_handler = logging.FileHandler('log-viewer.log')
f_handler.setLevel(logging.DEBUG)
f_handler.setFormatter(formatter)
logger.addHandler(f_handler)

s_handler = logging.StreamHandler()
s_handler.setLevel(logging.DEBUG)
s_handler.setFormatter(formatter)
logger.addHandler(s_handler)


class WebEngineView(QWidget):

    def __init__(self):
        super(WebEngineView, self).__init__()
        self.thread = None
        self.webEngineView = None
        self.initUI()

    def initUI(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        screen = app.primaryScreen()
        width = screen.size().width()
        height = screen.size().height()
        self.setCursor(QCursor(Qt.BlankCursor))

        # setting the minimum size
        self.setMinimumSize(width, height)
        self.webEngineView = QWebEngineView()
        self.webEngineView.setHtml("loading")
        vbox.addWidget(self.webEngineView)
        self.setLayout(vbox)

        self.thread = DisplayHandler()
        self.thread.default_template.connect(self.show_default_page)
        self.thread.user_template.connect(self.show_user_display)
        self.thread.start()

        self.showFullScreen()
        self.setWindowTitle('NoticeHome')
        self.show()

    def show_default_page(self, html):
        self.webEngineView.setHtml(html, baseUrl=QUrl(f"file://{settings['default_images_folder']}"))

    def show_user_display(self, html):
        self.webEngineView.setHtml(html, baseUrl=QUrl(f"file://{settings['images_folder']}"))


if __name__ == "__main__":
    logger.debug("Starting viewer")
    print("Starting viewer")
    window = WebEngineView()
    sys.exit(app.exec())
