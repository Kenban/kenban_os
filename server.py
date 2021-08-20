# This is Sam's attempt at rewriting the screenly server.py file
import os
from datetime import timedelta
from os import path
from random import randrange

import redis
from celery import Celery
from celery.schedules import crontab
from flask import Flask, request, render_template
from flask_cors import CORS
#from gunicorn.app.base import Application

from kenban.settings_kenban import settings as k_settings
from lib import assets_helper
from lib import db
from lib import queries
from lib.utils import get_node_ip
from settings import PORT, settings

__license__ = "Dual License: GPLv2 and Commercial License"

app = Flask(__name__)

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



################################
# Celery tasks
################################

@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    from kenban.sync import update_schedule
    sender.add_periodic_task(3600, update_schedule.s(), name='schedule_update')
    hour = randrange(0, 25)
    minute = randrange(0, 61)
    day = randrange(0, 8)
    sender.add_periodic_task(crontab(hour=hour, minute=minute, day_of_week=day), update_schedule.s(True), )


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

    foreground_image = k_settings["local_address"] + "/kenban_img/" + foreground_image_uuid  # Served by nginx
    template_filename = template_uuid
    return render_template(template_filename,
                           display_text=display_text,
                           foreground_image=foreground_image)


@app.route('/pair')
def pair():
    pair_code = request.args['user_code']
    verification_uri = request.args['verification_uri']
    if not verification_uri:
        verification_uri = "kenban.co.uk/pair"
    return render_template('pair.html', pair_code=pair_code, verification_uri=verification_uri)


@app.route('/splash-page')
def splash_page():
    return render_template('splash-page.html', my_ip=get_node_ip())


@app.before_first_request
def main():
    # Make sure the asset folder exist. If not, create it
    if not os.path.isdir(settings['assetdir']):
        os.mkdir(settings['assetdir'])
    # Create config dir if it doesn't exist
    if not path.isdir(settings.get_configdir()):
        os.makedirs(settings.get_configdir())

    with db.conn(settings['database']) as conn:
        with db.cursor(conn) as cursor:
            cursor.execute(queries.exists_table)
            if cursor.fetchone() is None:
                cursor.execute(assets_helper.create_assets_table)

    from kenban import schedule
    schedule.init_kenban()
    app.config['TEMPLATES_AUTO_RELOAD'] = True


if __name__ == "__main__":
    config = {
        'bind': '{}:{}'.format(settings.LISTEN, PORT),
        'threads': 2,
        'timeout': 20
    }
    app.run()


    # class GunicornApplication(Application):
    #     def init(self, parser, opts, args):
    #         return config
    #
    #     def load(self):
    #         return app


    #GunicornApplication().run()