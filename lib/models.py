from sqlalchemy import create_engine, Column, String, Time, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

from settings import settings

db_url = "sqlite:///" + settings["database"]
engine = create_engine(db_url, echo=True)
Base = declarative_base()
Session = sessionmaker(engine)


class ScheduleSlot(Base):
    __tablename__ = "schedule_slot"
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