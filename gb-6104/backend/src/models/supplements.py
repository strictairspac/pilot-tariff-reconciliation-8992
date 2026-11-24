from sqlalchemy import BigInteger, Column, Date, Integer, String, Table

from .base import metadata


# Supplement orders are registered once per leg (zone) and apply to every
# billing batch whose trips fall inside the stated service-date window. They
# never rewrite the original ledger: the issued-date side always resolves
# against the batch's own terms, and only the review side sees the order.
supplements = Table(
    "supplements", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("code", String(48), unique=True, nullable=False),
    Column("zone", String(30), nullable=False, index=True),
    Column("valid_from", Date, nullable=False),
    Column("valid_until", Date, nullable=True),
    Column("recorded_from", Date, nullable=False),
    Column("recorded_until", Date, nullable=True),
    Column("rate_cents", Integer, nullable=False),
    Column("min_cents", Integer, nullable=False),
    Column("note", String(500), nullable=False, default=""),
    Column("status", String(16), nullable=False, index=True),
    Column("failure", String(320), nullable=True),
    Column("digest", String(64), nullable=False),
    Column("attempts", Integer, nullable=False, default=0),
    Column("created_at", BigInteger, nullable=False),
    Column("created_by", String(48), nullable=False),
)
