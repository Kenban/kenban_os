import os
from os import path

import redis
from flask import Flask, request, render_template
from gunicorn.app.base import Application

from lib.models import Base, engine
from settings import PORT, LISTEN, settings

__license__ = "Dual License: GPLv2 and Commercial License"

template_folder = settings["templates_folder"] or '/data/kenban_templates/'
app = Flask(__name__, template_folder=template_folder)

r = redis.Redis(host='redis', port=6379, db=0)


@app.route('/kenban')
def kenban_display():
    """ The main display to show. Creates the display from url params"""
    template_uuid = request.args.get('template_uuid')
    display_text = request.args.get('display_text', default="")
    foreground_image_uuid = request.args.get('foreground_image_uuid', default="")
    event_text = request.args.get('event_text', default="")
    event_image_uuid = request.args.get('event_image_uuid', default="")

    banner_message = r.get("display-banner")

    if not template_uuid:
        return "Could not get template_uuid"

    image_folder_address = settings["local_address"] + "/img/"  # Served by nginx
    template_filename = template_uuid
    return render_template(template_filename,
                           image_folder_address=image_folder_address,
                           display_text=display_text,
                           foreground_image_uuid=foreground_image_uuid,
                           event_text=event_text,
                           event_image_uuid=event_image_uuid,
                           banner_message=banner_message)


@app.route('/hotspot')
def hotspot():
    ssid = request.args['ssid']
    ssid_password = request.args['ssid_password']
    return render_template('hotspot.html', ssid=ssid, ssid_password=ssid_password)


@app.route('/pair')
def pair():
    pair_code = request.args['user_code']
    verification_uri = request.args['verification_uri']
    if not verification_uri:
        verification_uri = "kenban.co.uk/pair"
    return render_template('pair.html', pair_code=pair_code, verification_uri=verification_uri)


@app.route('/splash-page')
def splash_page():
    return "splash page"


@app.route('/connect-error')
def connection_error():
    error = request.args['error']
    if not error:
        error = ""
    server_address = settings['server_address']
    return render_template('error.html', server_address=server_address, error=error)


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
