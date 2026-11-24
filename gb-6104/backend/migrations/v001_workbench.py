from sqlalchemy import inspect, text

from src.models import audit, cases, reviews, runs, supplement_applications, supplements, users  # noqa: F401
from src.models.base import metadata


def _add_missing_columns(connection):
    """Additive only: existing deployments get the new run snapshot column."""
    columns = {column["name"] for column in inspect(connection).get_columns("runs")}
    if "snapshot" not in columns:
        connection.execute(text("ALTER TABLE runs ADD COLUMN snapshot JSON NULL"))


def upgrade(connection):
    # Version 1 is additive and fully declarative.
    metadata.create_all(connection)
    _add_missing_columns(connection)
