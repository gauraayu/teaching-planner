import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, MetaData
from sqlalchemy import Uuid as _Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

# Deterministic constraint names.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Document-shaped columns (lists / objects). Stored as native arrays and objects in MongoDB.
JSONB = JSON


class Uuid(_Uuid):
    """Record identifier. Accepts a UUID or its string form, so an id read from JSON can be used directly."""

    def bind_processor(self, dialect):
        inner = super().bind_processor(dialect)

        def process(value):
            if isinstance(value, str):
                value = uuid.UUID(value)
            return inner(value) if inner else value

        return process


class UTCDateTime(TypeDecorator):
    """A moment in time. Always timezone-aware UTC in Python, whatever the storage keeps."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
        # MongoDB keeps milliseconds; hold exactly what it will hold, so a reload gives back identical values.
        return value.replace(microsecond=value.microsecond // 1000 * 1000)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)
