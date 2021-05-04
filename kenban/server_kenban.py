import logging
import os
from datetime import timedelta

from celery import Celery
from flask import Blueprint, request, render_template, current_app, url_for

import sync
from kenban import schedule
from settings_kenban import settings as k_settings

#todo think we need to add zmq to requirements

bp = Blueprint('kenban', __name__,
               template_folder='templates')

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

    foreground_image = "kenban_img/" + foreground_image_uuid
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


# TODO Trigger a force update once per week(day?) to ensure existing templates are up to date
@celery.task()
def update_schedule(force=False):
    logging.debug("Checking for update")
    local_update_time = k_settings["last_update"]
    server_update_time = sync.get_server_last_update_time()
    if local_update_time != server_update_time or force:
        sync.get_all_images()
        sync.get_all_templates()
        sync.get_schedule()
        sync.get_all_events()
        schedule.build_assets_table()

    k_settings["last_update"] = server_update_time  # todo test this is a date before saving
    k_settings.save()


@celery.on_after_finalize.connect
def setup_periodic_kenban_tasks(sender, **kwargs):
    sender.add_periodic_task(10, update_schedule.s(), name='schedule_update')
