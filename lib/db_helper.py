import logging

from dateutil.parser import parse

from lib.models import Session, ScheduleSlot, Event
from lib.utils import time_parser


def save_schedule_slot(session: Session, slot: ScheduleSlot):
    logging.debug("Saving schedule slot")
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


def save_event(session: Session, event: Event):
    logging.debug("Saving event")
    db_event = session.query(Event).filter_by(uuid=event["uuid"]).first()
    if not db_event:
        db_event = ScheduleSlot()
        session.add(db_event)
    db_event.uuid = event["uuid"]
    db_event.foreground_image_uuid = event["foreground_image_uuid"]
    db_event.display_text = event["display_text"]
    db_event.event_start = parse(event["event_start"])
    db_event.event_end = parse(event["event_end"])
    db_event.override = event["override"]
