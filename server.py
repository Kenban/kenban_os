import os
from datetime import timedelta
from os import path
from random import randrange

import redis
from celery import Celery
from flask import Flask, request, render_template
from flask_cors import CORS
from gunicorn.app.base import Application

from lib.models import Base, engine
from lib.utils import get_node_ip
from settings import PORT, LISTEN, settings

__license__ = "Dual License: GPLv2 and Commercial License"

template_folder = settings["templates_folder"] or '/data/kenban_templates/'
app = Flask(__name__, template_folder=template_folder)

CORS(app)

r = redis.Redis(host='redis', port=6379, db=0)

HOME = os.getenv('HOME', '/home/pi')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_TASK_RESULT_EXPIRES = timedelta(hours=6)

celery = Celery(
    app.name,
    backend=CELERY_RESULT_BACKEND,
    broker=CELERY_BROKER_URL,
    result_expires=CELERY_TASK_RESULT_EXPIRES
)

try:
    my_ip = get_node_ip()
except Exception:
    pass


@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # todo set full sync task up properly
    # sender.add_periodic_task(3600, full_sync.s(), name='schedule_update')
    hour = randrange(0, 25)
    minute = randrange(0, 61)
    day = randrange(0, 8)
    # sender.add_periodic_task(crontab(hour=hour, minute=minute, day_of_week=day), update_schedule.s(True), )


@app.route('/kenban')
def kenban_display():
    """ The main display to show. Creates the display from url params"""
    display_text = request.args.get('display_text')
    foreground_image_uuid = request.args.get('foreground_image_uuid')
    template_uuid = request.args.get('template_uuid')

    if not display_text:
        return "Could not get display_text"
    if not foreground_image_uuid:
        return "Could not get foreground_image_uuid"
    if not template_uuid:
        return "Could not get template_uuid"

    image_folder_address = settings["local_address"] + "/img/"  # Served by nginx
    template_filename = template_uuid
    return render_template(template_filename,
                           image_folder_address=image_folder_address,
                           display_text=display_text,
                           foreground_image_uuid=foreground_image_uuid)


@app.route('/pair')
def pair():
    pair_code = request.args['user_code']
    verification_uri = request.args['verification_uri']
    if not verification_uri:
        verification_uri = "kenban.co.uk/pair"
    return template('pair.html', pair_code=pair_code, verification_uri=verification_uri)


@app.route('/splash-page')
def splash_page():
    return "splash page"


@app.route('/connect-error')
def connection_error():
    return "Error connecting to Kenban server"


# TODO Can probably remove this once we nail down which ones we need
def template(template_name, **context):
    """Kenban template response generator. Shares the
    same function signature as Flask's render_template() method
    but also injects some global context."""

    # Add global contexts
    context['date_format'] = settings['date_format']
    context['default_duration'] = settings['default_duration']
    context['default_streaming_duration'] = settings['default_streaming_duration']
    context['template_settings'] = {
        'imports': ['from lib.utils import template_handle_unicode'],
        'default_filters': ['template_handle_unicode'],
    }
    context['use_24_hour_clock'] = settings['use_24_hour_clock']

    return render_template(template_name, context=context)


if __name__ == "__main__":
    # Create config dir if it doesn't exist
    if not path.isdir(settings.get_configdir()):
        os.makedirs(settings.get_configdir())
    # Create images and templates folder if they don't exist
    if not os.path.isdir(settings['images_folder']):
        os.mkdir(settings['images_folder'])
    # Create config dir if it doesn't exist
    if not os.path.isdir(settings['templates_folder']):
        os.mkdir(settings['templates_folder'])

    # Initialise database
    Base.metadata.create_all(engine)

    app.config['TEMPLATES_AUTO_RELOAD'] = True
    config = {
        'bind': '{}:{}'.format(LISTEN, PORT),
        'threads': 2,
        'timeout': 20
    }


    class GunicornApplication(Application):
        def init(self, parser, opts, args):
            return config

        def load(self):
            return app


    GunicornApplication().run()
