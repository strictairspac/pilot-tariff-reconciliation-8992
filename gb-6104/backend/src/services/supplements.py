from datetime import date
from time import time

from fastapi import HTTPException
from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from src.constants.supplement_state import SupplementState
from src.domain.supplement_rules import fingerprint, normalize
from src.models.supplement_applications import applications
from src.models.supplements import supplements
from .audit import record


def _entry(row):
    return dict(row)


def get(db, supplement_id, for_update=False):
    statement = select(supplements).where(supplements.c.id == supplement_id)
    if for_update:
        statement = statement.with_for_update()
    row = db.execute(statement).mappings().first()
    if row is None:
        raise HTTPException(404, "补录单不存在")
    return _entry(row)


def by_code(db, code, for_update=False):
    statement = select(supplements).where(supplements.c.code == code)
    if for_update:
        statement = statement.with_for_update()
    return db.execute(statement).mappings().first()


def list_entries(db, zone=None):
    statement = select(supplements)
    if zone is not None:
        statement = statement.where(supplements.c.zone == zone)
    statement = statement.order_by(supplements.c.id.desc()).limit(200)
    return [dict(row) for row in db.execute(statement).mappings()]


def _overlaps(db, zone, valid_from, valid_until, exclude_id=None):
    """Return the active supplements on the same leg sharing any service date."""
    rows = db.execute(
        select(supplements).where(
            supplements.c.zone == zone, supplements.c.status == SupplementState.ACTIVE,
        ).with_for_update()
    ).mappings().all()
    conflicts = []
    for row in rows:
        if exclude_id is not None and row["id"] == exclude_id:
            continue
        if (valid_until is None or row["valid_from"] < valid_until) and (
            row["valid_until"] is None or valid_from < row["valid_until"]
        ):
            conflicts.append(row)
    return conflicts


def create(db, data, actor):
    """Register one supplement order for a single leg.

    The order number is the idempotency key: replaying the same content
    returns the stored order, while reusing the number with different content
    is rejected so an already-effective order cannot be silently rewritten.
    """
    values = normalize(data)
    digest = fingerprint(values)
    existing = by_code(db, values["code"], for_update=True)
    if existing is not None:
        if existing["digest"] != digest:
            raise HTTPException(409, f"补录单号 {values['code']} 已存在且内容不同，请退回原单")
        return _entry(existing)
    conflicts = _overlaps(db, values["zone"], values["valid_from"], values["valid_until"])
    state = SupplementState.ACTIVE
    failure = None
    if conflicts:
        state = SupplementState.FAILED
        failure = f"与已生效补录单 {conflicts[0]['code']} 的服务日期重叠"[:320]
    try:
        change = db.execute(insert(supplements).values(
            code=values["code"], zone=values["zone"],
            valid_from=values["valid_from"], valid_until=values["valid_until"],
            recorded_from=values["recorded_from"], recorded_until=None,
            rate_cents=values["rate"], min_cents=values["minimum"], note=values["note"],
            status=state, failure=failure, digest=digest, attempts=0,
            created_at=int(time()), created_by=actor,
        ))
    except IntegrityError as exc:
        # A concurrent registration won the same order number; apply the same
        # rule: identical content reads back the stored order, different
        # content is rejected.
        existing = by_code(db, values["code"], for_update=True)
        if existing is not None and existing["digest"] == digest:
            return _entry(existing)
        raise HTTPException(409, f"补录单号 {values['code']} 已存在且内容不同，请退回原单") from exc
    supplement_id = change.inserted_primary_key[0]
    record(db, "register_supplement", actor, "supplement", supplement_id)
    return get(db, supplement_id)


def retry(db, supplement_id, actor):
    """Re-try a failed order without changing its content.

    Content edits are refused elsewhere; retry only re-checks the leg for
    conflicts and re-activates the same recorded version.
    """
    supplement = get(db, supplement_id, for_update=True)
    if supplement["status"] == SupplementState.ACTIVE:
        return supplement
    if supplement["status"] == SupplementState.RETIRED:
        raise HTTPException(409, "已退回的补录单不能重试，请重新登记")
    conflicts = _overlaps(
        db, supplement["zone"], supplement["valid_from"], supplement["valid_until"], supplement["id"]
    )
    if conflicts:
        db.execute(update(supplements).where(supplements.c.id == supplement_id).values(
            attempts=supplement["attempts"] + 1,
            failure=f"与已生效补录单 {conflicts[0]['code']} 的服务日期重叠"[:320],
        ))
        record(db, "retry_supplement", actor, "supplement", supplement_id)
        return get(db, supplement_id)
    db.execute(update(supplements).where(supplements.c.id == supplement_id).values(
        status=SupplementState.ACTIVE, failure=None,
        attempts=supplement["attempts"] + 1,
    ))
    record(db, "retry_supplement", actor, "supplement", supplement_id)
    return get(db, supplement_id)


def retire(db, supplement_id, actor):
    """Withdraw an order so a corrected one can be registered under a new number."""
    supplement = get(db, supplement_id, for_update=True)
    if supplement["status"] == SupplementState.RETIRED:
        return supplement
    db.execute(update(supplements).where(supplements.c.id == supplement_id).values(
        status=SupplementState.RETIRED,
    ))
    record(db, "retire_supplement", actor, "supplement", supplement_id)
    return get(db, supplement_id)


def snapshot(db, zone_set):
    """Freeze the versions in effect when a batch is accepted.

    The read takes row locks so a concurrent registration cannot slip between
    "what is active" and "what the batch recorded"; the worker later uses only
    this snapshot and never re-reads the live table. Active orders take part
    in pricing. Failed orders are carried as `blocked`: their dates are held
    on that leg only, so an order stuck on one leg never stalls the others.
    Retired orders are not accepted by any new batch.
    """
    rows = db.execute(
        select(supplements).where(
            supplements.c.zone.in_(sorted(zone_set)),
            supplements.c.status.in_([SupplementState.ACTIVE, SupplementState.FAILED]),
        ).order_by(supplements.c.id).with_for_update()
    ).mappings().all()
    accepted_rows, blocked_rows = [], []
    for row in rows:
        (accepted_rows if row["status"] == SupplementState.ACTIVE else blocked_rows).append(row)
    accepted = [{
        "code": row["code"], "zone": row["zone"],
        "valid_from": row["valid_from"].isoformat(),
        "valid_until": row["valid_until"].isoformat() if row["valid_until"] else None,
        "recorded_from": row["recorded_from"].isoformat(),
        "rate": row["rate_cents"], "minimum": row["min_cents"],
    } for row in accepted_rows]
    blocked = [{
        "code": row["code"], "zone": row["zone"],
        "valid_from": row["valid_from"].isoformat(),
        "valid_until": row["valid_until"].isoformat() if row["valid_until"] else None,
        "reason": row["failure"],
    } for row in blocked_rows]
    return {"supplements": accepted, "blocked": blocked, "accepted_at": int(time())}


def record_applications(db, run_id, accepted, applied_codes):
    """Persist that an accepted version took part in a run, at most once.

    `applied_codes` are the orders that actually touched a trip; an order that
    covers no trip in this batch was accepted but did not change any charge.
    The unique key means a retried run cannot make the same order effective
    twice.
    """
    by_code_map = {entry["code"]: entry for entry in accepted}
    for code in sorted(set(applied_codes)):
        entry = by_code_map.get(code)
        if entry is None:
            continue
        supplement_id = db.execute(
            select(supplements.c.id).where(supplements.c.code == code)
        ).scalar_one()
        exists = db.execute(
            select(applications.c.id).where(
                applications.c.supplement_id == supplement_id, applications.c.run_id == run_id,
            )
        ).first()
        if exists is not None:
            continue
        db.execute(insert(applications).values(
            supplement_id=supplement_id, run_id=run_id, supplement_code=code, zone=entry["zone"],
            valid_from=date.fromisoformat(entry["valid_from"]),
            valid_until=date.fromisoformat(entry["valid_until"]) if entry["valid_until"] else None,
            rate_cents=entry["rate"], min_cents=entry["minimum"], created_at=int(time()),
        ))


def applications_for(db, run_id):
    rows = db.execute(
        select(applications).where(applications.c.run_id == run_id).order_by(applications.c.id)
    ).mappings()
    return [{
        **dict(row),
        "valid_from": row["valid_from"].isoformat(),
        "valid_until": row["valid_until"].isoformat() if row["valid_until"] else None,
    } for row in rows]
