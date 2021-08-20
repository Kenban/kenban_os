from flask import Blueprint, request, render_template

from settings import settings

bp = Blueprint('kenban', __name__,
               template_folder=settings["templates_folder"])



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

    foreground_image = settings["local_address"] + "/kenban_img/" + foreground_image_uuid  # Served by nginx
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
