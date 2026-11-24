from sqlalchemy import BigInteger, Column, Date, ForeignKey, Integer, String, Table, UniqueConstraint

from .base import metadata


# One row per (supplement, run) application. The unique key makes an order
# effective at most once inside a billing batch even when the run is retried.
applications = Table(
    "supplement_applications", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("supplement_id", ForeignKey("supplements.id"), nullable=False, index=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False, index=True),
    Column("supplement_code", String(48), nullable=False),
    Column("zone", String(30), nullable=False),
    Column("valid_from", Date, nullable=False),
    Column("valid_until", Date, nullable=True),
    Column("rate_cents", Integer, nullable=False),
    Column("min_cents", Integer, nullable=False),
    Column("created_at", BigInteger, nullable=False),
    UniqueConstraint("supplement_id", "run_id", name="uq_supplement_run"),
)
