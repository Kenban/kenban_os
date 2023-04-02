import logging.config
import sys

from PyQt5.QtCore import QUrl, Qt
from PyQt5.QtGui import QCursor
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout
from jinja2 import Environment, FileSystemLoader, select_autoescape

from lib.display_handler import DisplayHandler
from lib.models import Base, engine
from settings import settings

Base.metadata.create_all(engine)

app = QApplication(sys.argv)

logs_path = Path("logs")
logs_path.mkdir(exist_ok=True)
logging.config.fileConfig(fname='logging.ini', disable_existing_loggers=True)
logger = logging.getLogger("viewer")

default_templates_env = Environment(
    loader=FileSystemLoader(settings["default_templates_folder"]),
    autoescape=select_autoescape()
)


class WebEngineView(QWidget):

    def __init__(self):
        super(WebEngineView, self).__init__()
        self.thread = None
        self.webEngineView = None
        self.initUI()

    # noinspection PyPep8Naming
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
        html = default_templates_env.get_template("loading.html").render()
        self.webEngineView.setHtml(html, baseUrl=QUrl(f"file://{settings['default_images_folder']}"))
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
