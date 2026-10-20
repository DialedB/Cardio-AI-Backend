"""Domain persistence models; intentionally empty until the schema is agreed."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all persisted SQLAlchemy models."""
    pass
