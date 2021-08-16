import os
from datetime import timedelta

from celery import Celery
from flask import Blueprint, request, render_template

from settings_kenban import settings as k_settings

bp = Blueprint('kenban', __name__,
               template_folder=k_settings["templates_folder"])

CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_TASK_RESULT_EXPIRES = timedelta(hours=6)

celery = Celery(
    "kenban",
    backend=CELERY_RESULT_BACKEND,
    broker=CELERY_BROKER_URL,
    result_expires=CELERY_TASK_RESULT_EXPIRES
)


@bp.route('/kenban')
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


@bp.route('/pair')
def pair():
    pair_code = request.args['user_code']
    verification_uri = request.args['verification_uri']
    if not verification_uri:
        verification_uri = "kenban.co.uk/pair"
    return render_template('pair.html', pair_code=pair_code, verification_uri=verification_uri)
