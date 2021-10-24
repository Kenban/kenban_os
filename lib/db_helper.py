from lib.models import Session, ScheduleSlot
from lib.utils import time_parser


def save_schedule_slot(session: Session, slot: ScheduleSlot):
    db_slot = session.query(ScheduleSlot).filter_by(uuid=slot["uuid"]).first()
    if not db_slot:
        db_slot = ScheduleSlot()
        session.add(db_slot)
    db_slot.uuid = slot["uuid"]
    db_slot.template_uuid = slot["template_uuid"]
    db_slot.foreground_image_uuid = slot["foreground_image_uuid"]
    db_slot.display_text = slot["display_text"]
    db_slot.time_format = slot["time_format"]
    db_slot.start_time = time_parser(slot["start_time"])
    db_slot.weekday = slot["weekday"]