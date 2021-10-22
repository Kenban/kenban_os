import logging

from lib.models import db_url, Session, ScheduleSlot
from lib.utils import get_db_mtime

logging.info(f"using db {db_url}")


def get_schedule_slot_uuids():
    session = Session()
    return session.query(ScheduleSlot.uuid).all()


def get_event_uuids():
    session = Session()
    return session.query(ScheduleSlot.uuid).all()


class Scheduler(object):
    def __init__(self):
        logging.debug('Scheduler init')
        self.slots = []
        self.current_slot = None
        self.last_update_db_mtime = None
        self.update_playlist()

    def get_current_schedule_slot(self):
        # todo
        session = Session()
        session.query(ScheduleSlot).get(1)
        session.close()
        pass

    def refresh_playlist(self):
        logging.debug('refresh_playlist')
        if get_db_mtime() > self.last_update_db_mtime:
            logging.debug('updating playlist due to database modification')
            self.update_playlist()

    def update_playlist(self):
        logging.debug('update_playlist')
        self.last_update_db_mtime = get_db_mtime()
        session = Session()
        new_slots = session.query(ScheduleSlot).all()
        session.close()
        if new_slots == self.slots:
            # If nothing changed, do nothing
            return
        self.slots = new_slots
        logging.info("Playlist updated")

# def get_specific_asset(asset_id):
#     # FIXME
#     logging.info('Getting specific asset')
#     #return assets_helper.read(db_conn, asset_id)
#
#
# def generate_asset_list():
#
#     """Choose deadline via:
#         1. Map assets to deadlines with rule: if asset is active then 'end_date' else 'start_date'
#         2. Get nearest deadline
#     """
#     logging.info('Generating asset-list...')
#     # FIXME
#     #assets = assets_helper.read(db_conn)
#     assets= []
#     deadlines = [asset['end_date'] if assets_helper.is_active(asset) else asset['start_date'] for asset in assets]
#
#     playlist = list(filter(assets_helper.is_active, assets))
#     deadline = sorted(deadlines)[0] if len(deadlines) > 0 else None
#     logging.debug('generate_asset_list deadline: %s', deadline)
#
#     if settings['shuffle_playlist']:
#         shuffle(playlist)
#
#     return playlist, deadline

if __name__ == "__main__":
    scheduler = Scheduler()
    scheduler.get_current_schedule_slot()