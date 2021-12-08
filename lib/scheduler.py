import logging
from datetime import datetime, timedelta
from typing import List

from lib.models import ScheduleSlot, Event, Session
from lib.utils import WEEKDAY_DICT, get_db_mtime


class Scheduler(object):
    def __init__(self):
        self.last_update_db_mtime = None
        self.slots: List[ScheduleSlot] = []
        self.current_slot = None
        self.current_slot_index = None
        self.next_slot = None
        self.events: List[Event] = []
        self.event_active = False
        self.active_events: List[Event] = []
        self.daily_events: List[Event] = []
        self.daily_events_date = None  # To check if events have been collected today
        self.update_assets_from_db()
        self.calculate_current_slot()
        self.calculate_daily_events()
        self.calculate_current_events()

    def set_current_slot(self, slot):
        if not slot:
            logging.debug(f"SlotHandler: No slot found")
            self.current_slot = None
            return
        logging.debug(f"Setting current slot to {slot.uuid}")
        self.current_slot = slot
        self.current_slot_index = self.slots.index(slot)
        # Check if it's the last in the list
        if len(self.slots) - 1 == self.current_slot_index:
            self.next_slot = self.slots[0]
        else:
            self.next_slot = self.slots[self.current_slot_index + 1]

    def sort_slots(self):
        """ Order the list of slots chronologically"""
        self.slots.sort(key=lambda s: s.start_time)
        self.slots.sort(key=lambda s: WEEKDAY_DICT[s.weekday])

    def tick(self):
        """ Check if it's time for the next slot in the order, and switch if so"""
        if not self.next_slot:
            logging.info("No next slot set")
        elif WEEKDAY_DICT[self.next_slot.weekday] == datetime.now().weekday() and \
                datetime.now().time() > self.next_slot.start_time:
            self.set_current_slot(self.next_slot)

        if self.daily_events_date != datetime.now().date():
            self.calculate_daily_events()

        self.calculate_current_events()

    def calculate_current_slot(self):
        """ Return the slot that should currently be active according to times """
        this_weekday = datetime.now().strftime("%A")
        current_time = datetime.now().time()
        days_slots = list(filter(lambda s: s.weekday == this_weekday, self.slots))  # Get today's slots
        eligible_slots = list(filter(lambda s: s.start_time < current_time, days_slots))  # Filter out future slots
        if len(eligible_slots) == 0:
            logging.warning("Could not find slot for this time")
        else:
            self.set_current_slot(max(eligible_slots, key=lambda s: s.start_time))

    def calculate_daily_events(self):
        """ Get events that will occur today (to avoid sorting through all events every tick) """
        today = datetime.now()
        # Add a couple hours buffer either way, it wont hurt and it will stop unexpected dst shenanigans
        day_start = datetime(year=today.year, month=today.month, day=today.day) - timedelta(2)
        day_end = datetime(year=today.year, month=today.month, day=today.day, hour=23) + timedelta(3)
        self.daily_events = [e for e in self.events
                             if (e.event_start < day_start > e.event_end)  # Starts before day, ends during/after day
                             or (day_start < e.event_start < day_end)]  # Starts during day
        self.daily_events_date = today.date()

    def calculate_current_events(self):
        self.active_events = [e for e in self.daily_events if e.event_start < datetime.now() < e.event_end]
        if len(self.active_events) > 0:
            self.event_active = True
        else:
            self.event_active = False

    def update_assets_from_db(self):
        """ Load the slots from the database into the scheduler """
        logging.debug("Loading assets into slot handler")
        self.last_update_db_mtime = get_db_mtime()
        session = Session()
        new_slots = session.query(ScheduleSlot).all()
        new_events = session.query(Event).all()
        session.close()
        if new_slots == self.slots and new_events == self.events:
            # If nothing changed, do nothing
            logging.debug("No change in assets")
            return
        self.slots = new_slots
        self.sort_slots()
        self.calculate_current_slot()
        for e in new_events:
            if e.event_end < datetime.now():
                new_events.remove(e)
        self.events = new_events
        self.calculate_daily_events()
