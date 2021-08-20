


# todo rewrite all of this. Use sqlalchemy and make it neater






import datetime
import logging
import os
import uuid

import pytz
from dateutil.tz import tzlocal
from sqlalchemy import create_engine, Table, MetaData, Column, String, Time, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base

from lib import db, assets_helper
from settings import settings

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

create_schedule_table = 'CREATE TABLE IF NOT EXISTS schedule(id integer primary key, uuid text NOT NULL, template_uuid text NOT NULL, foreground_image_uuid text, display_text text , time_format integer, start_time time, weekday text)'
create_event_table = 'CREATE TABLE IF NOT EXISTS event(id integer primary key, uuid text NOT NULL, foreground_image_uuid text, display_text text , event_start time, event_end time, override integer)'

comma = ','.join
quest = lambda l: '=?,'.join(l) + '=?'

read_all_schedule = lambda keys: 'select ' + comma(keys) + ' from assets order by play_order'
create_schedule = lambda keys: 'insert into schedule (' + comma(keys) + ') values (' + comma(['?'] * len(keys)) + ')'
update_schedule = lambda keys: 'update schedule set ' + quest(keys) + ' where uuid=?'
create_event = lambda keys: 'insert into event (' + comma(keys) + ') values (' + comma(['?'] * len(keys)) + ')'
update_event = lambda keys: 'update event set ' + quest(keys) + ' where uuid=?'

db_url = "sqlite:///" + settings["database"]
engine = create_engine('sqlite:///kenban.db')
Base = declarative_base()
Session = sessionmaker(engine)


class Schedule(Base):
    __tablename__ = "schedule"
    uuid = Column(String, primary_key=True)
    template_uuid = Column(String)
    foreground_image_uuid = Column(String)
    display_text = Column(String)
    time_format = Column(String)
    start_time = Column(Time)
    weekday = Column(String)


class Event(Base):
    __tablename__ = "event"
    uuid = Column(String, primary_key=True)
    template_uuid = Column(String)
    foreground_image_uuid = Column(String)
    display_text = Column(String)
    time_format = Column(String)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    weekday = Column(String)


def init_kenban_new():
    # Create images and templates folder if they don't exist
    if not os.path.isdir(settings['images_folder']):
        os.mkdir(settings['images_folder'])
    # Create config dir if it doesn't exist
    if not os.path.isdir(settings['templates_folder']):
        os.mkdir(settings['templates_folder'])

    # Initialise database
    Base.metadata.create_all(engine)


def get_schedule_slot_uuids():
    session = Session()
    return session.query(Schedule.uuid).all()


def get_event_uuids():
    with db.conn(settings['database']) as conn:
        with db.cursor(conn) as c:
            c.execute('select uuid from event')
            return [uuid[0] for uuid in c.fetchall()]






def dict_factory(cursor, row):
    """ Helper function for sqlite3 to return a dict"""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def init_kenban():
    # Create images and templates folder if they don't exist
    if not os.path.isdir(settings['images_folder']):
        os.mkdir(settings['images_folder'])
    # Create config dir if it doesn't exist
    if not os.path.isdir(settings['templates_folder']):
        os.mkdir(settings['templates_folder'])

    # Create database tables if they don't exist
    with db.conn(settings['database']) as conn:
        with db.cursor(conn) as cursor:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schedule'")
            if cursor.fetchone() is None:
                cursor.execute(create_schedule_table)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
            if cursor.fetchone() is None:
                cursor.execute(create_event_table)





def get_schedule_slot_uuids():
    with db.conn(settings['database']) as conn:
        with db.cursor(conn) as c:
            c.execute('select uuid from schedule')
            return [uuid[0] for uuid in c.fetchall()]


def save_schedule_slot(slot, update):
    db_slot = {"uuid": slot["uuid"],
               "template_uuid": slot["template_uuid"],
               "foreground_image_uuid": slot["foreground_image_uuid"],
               "display_text": slot["display_text"],
               "time_format": slot["time_format"],
               "start_time": slot["start_time"],
               "weekday": slot["weekday"]}
    with db.conn(settings['database']) as conn:
        if update:
            with db.commit(conn) as c:
                c.execute(update_schedule(db_slot.keys()), db_slot.values() + [db_slot["uuid"]])
        else:
            conn.execute(create_schedule(db_slot.keys()), db_slot.values())


def get_event_uuids():
    with db.conn(settings['database']) as conn:
        with db.cursor(conn) as c:
            c.execute('select uuid from event')
            return [uuid[0] for uuid in c.fetchall()]


def save_event(event, update):
    db_event = {"uuid": event["uuid"],
                "foreground_image_uuid": event["foreground_image_uuid"],
                "display_text": event["display_text"],
                "event_start": event["event_start"],
                "event_end": event["event_end"],
                "override": event["override"]}
    with db.conn(settings['database']) as conn:
        if update:
            with db.commit(conn) as c:
                c.execute(update_event(db_event.keys()), db_event.values() + [db_event["uuid"]])
        else:
            conn.execute(create_event(db_event.keys()), db_event.values())


def build_assets_table():
    """ Use the kenban schedule and event table to build the assets table used by screenly"""
    with db.conn(settings['database']) as conn:
        conn.row_factory = dict_factory
        with db.cursor(conn) as c:
            c.execute('select * from schedule')
            schedule_slots = c.fetchall()
            c.execute('select * from event')
            events = c.fetchall()
            c.execute('delete from assets')

    # Parse the times
    for slot in schedule_slots:
        # This gets the start time in UTC to save in the database. It's messy but when I made it shorter it broke
        slot_start_local = datetime.datetime.strptime(slot["start_time"], "%H:%M:%S")
        as_full_datetime = datetime.datetime.now(tz=tzlocal())\
            .replace(hour=slot_start_local.hour, minute=0, second=0, microsecond=0)
        utc_start = as_full_datetime.astimezone(pytz.utc)
        slot["start_time"] = utc_start.time()

    for event in events:
        try:
            event["event_start"] = datetime.datetime.strptime(event["event_start"], "%Y-%m-%dT%H:%M:%S+00:00")
            event["event_end"] = datetime.datetime.strptime(event["event_end"], "%Y-%m-%dT%H:%M:%S+00:00")
        except ValueError:
            logging.error("Failed converting event datetime")
        # if we ever convert to python3, use datetime.isoformat() instead of this mess
        # The current method assumes utc which it should always be but ya never know
    # TODO Dont use utc to set the times for daily schedules. i dont know why i tried to do this anyway
    # Put slots in a dict according to the weekday
    day_slots = {}
    for day in WEEKDAYS:
        day_slots[day] = []
        for slot in schedule_slots:
            if slot["weekday"] == day:
                day_slots[day].append(slot)
        # Sort the slots according to start time
        day_slots[day].sort(key=lambda x: x["start_time"])
        for x in range(0, len(day_slots[day])-1):
            day_slots[day][x]["end_time"] = day_slots[day][x+1]["start_time"]
        # The last slot of the day finishes at 23:59
        if day_slots[day]:
            # Create 23:59 in local time and convert it to UTC
            end = datetime.datetime.now(tz=tzlocal()).replace(hour=23, minute=59, second=59, microsecond=9999)
            day_slots[day][-1]["end_time"] = end.astimezone(pytz.utc).replace(tzinfo=None).time()

    # Loop through the days of the upcoming week and apply the schedule
    # Create 00:00 in local time and convert to UTC
    midnight = datetime.datetime.now(tz=tzlocal()).replace(hour=0, minute=0, second=0, microsecond=0)
    utc_midnight_in_local_time = midnight.astimezone(pytz.utc)
    for x in range(0, 7):
        day_start = utc_midnight_in_local_time + datetime.timedelta(days=x)
        day_end = utc_midnight_in_local_time + datetime.timedelta(days=x+1)

        # Loop through every slot on this day and create an asset
        day_name = day_start.strftime("%A")
        for slot in day_slots[day_name]:
            asset_start = datetime.datetime.combine(day_start.date(), slot["start_time"])
            asset_end = datetime.datetime.combine(day_end.date(), slot["end_time"])
            # Check if any events are during this period
            for event in events:
                if day_start <= event["event_start"] <= day_end:
                    create_asset_from_event(event, slot)
            create_asset_from_schedule_slot(schedule_slot=slot, start=asset_start, end=asset_end)


def create_asset_from_schedule_slot(schedule_slot, start, end):
    base_uri = settings['local_address']
    asset_uri = base_uri + "/kenban?foreground_image_uuid={image}&display_text={text}&template_uuid={template}".format(
        image=schedule_slot["foreground_image_uuid"],
        text=schedule_slot["display_text"],
        template=schedule_slot["template_uuid"]
    )
    asset_id = uuid.uuid4().hex
    asset = {
        "asset_id": asset_id,
        "mimetype": "webpage",
        "is_enabled": 1,
        "name": schedule_slot["uuid"],
        "end_date": end,
        "duration": "10",
        "play_order": 0,
        "nocache": 0,
        "uri": asset_uri,
        "skip_asset_check": 1,
        "start_date": start
    }
    with db.conn(settings['database']) as conn:
        assets_helper.create(conn, asset)


def create_asset_from_event(event, schedule_slot):
    base_uri = settings['local_address']
    asset_uri = base_uri + "/kenban?foreground_image_uuid={image}&display_text={text}&template_uuid={template}".format(
        image=event["foreground_image_uuid"],
        text=event["display_text"],
        template=schedule_slot["template_uuid"]
    )
    import uuid
    asset_id = uuid.uuid4().hex
    asset = {
        "asset_id": asset_id,
        "mimetype": "webpage",
        "is_enabled": 1,
        "name": event["uuid"],
        "end_date": event["event_end"],
        "duration": "10",
        "play_order": 0,
        "nocache": 0,
        "uri": asset_uri,
        "skip_asset_check": 1,
        "start_date": event["event_start"]
    }
    with db.conn(settings['database']) as conn:
        assets_helper.create(conn, asset)
