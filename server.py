import os
from os import path

from flask import Flask, request, render_template

from lib.models import Base, engine
from settings import settings

__license__ = "Dual License: GPLv2 and Commercial License"

# Create dirs if they doesn't exist
if not path.isdir(settings.get_configdir()):
    os.makedirs(settings.get_configdir())
if not os.path.isdir(settings['images_folder']):
    os.mkdir(settings['images_folder'])
if not os.path.isdir(settings['templates_folder']):
    os.mkdir(settings['templates_folder'])

Base.metadata.create_all(engine)

template_folder = settings["templates_folder"] or '/data/kenban_templates/'
app = Flask(__name__, template_folder=template_folder)
app.config['TEMPLATES_AUTO_RELOAD'] = True


@app.route('/kenban')
def kenban_display():
    """ The main display to show. Creates the display from url params"""
    template_uuid = request.args.get('template_uuid')
    display_text = request.args.get('display_text', default="")
    foreground_image_uuid = request.args.get('foreground_image_uuid', default="")
    event_text = request.args.get('event_text', default="")
    event_image_uuid = request.args.get('event_image_uuid', default="")

    banner_message = request.args.get('banner_message', default="")

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


@app.route('/error')
def connection_error():
    message = request.args['message']
    return render_template('error.html', message=message)


# @app.errorhandler(404)
# def page_not_found(e):
#     return render_template('error.html'), 404

