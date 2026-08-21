"""Anonymous marketing-site events.

Rows are written by ``POST /telemetry/event``. Deliberately a plain table
rather than a warehouse: at marketing-site volume this is a few thousand
rows a month, which Postgres aggregates instantly and keeps forever,
where Cloud Logging drops everything after 30 days.

Nothing here identifies a person. ``visitor`` is a daily-rotating salted
hash (see ``routers/telemetry.py``) that exists only so "visits" can be
told apart from "pageviews" within a single day.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String

from app.database import Base


class WebEvent(Base):
    __tablename__ = "web_events"

    id = Column(Integer, primary_key=True, index=True)
    event = Column(String(64), nullable=False, index=True)
    # Which instance of a repeated control fired it ("hero", "nav", ...).
    location = Column(String(64), nullable=True)
    path = Column(String(200), nullable=True)
    visitor = Column(String(32), nullable=True, index=True)
    referrer = Column(String(300), nullable=True)
    utm_source = Column(String(100), nullable=True, index=True)
    utm_medium = Column(String(100), nullable=True)
    utm_campaign = Column(String(100), nullable=True)
    lang = Column(String(5), nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.utcnow(), nullable=False, index=True
    )

    # Every admin-traffic query is "this event, over this window".
    __table_args__ = (Index("ix_web_events_event_created", "event", "created_at"),)
