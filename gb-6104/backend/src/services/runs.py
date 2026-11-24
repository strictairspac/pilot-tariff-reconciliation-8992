from time import time

from fastapi import HTTPException
from sqlalchemy import insert, select

from src.constants.job_state import JobState
from src.domain.scenario import CONFIG
from src.models.cases import cases
from src.models.runs import runs
from . import audit, cases as case_service, supplements


def query():
    return select(runs, cases.c.title.label("case_title")).join(cases, cases.c.id == runs.c.case_id)


def get(db, run_id):
    run = db.execute(query().where(runs.c.id == run_id)).mappings().first()
    if run is None:
        raise HTTPException(404, "执行批次不存在")
    entry = dict(run)
    entry["supplements"] = supplements.applications_for(db, run_id)
    return entry


def list_entries(db):
    return [dict(row) for row in db.execute(query().order_by(runs.c.id.desc()).limit(100)).mappings()]


def versions(db, run_id):
    """Versions the batch actually priced with, for review readback."""
    run = get(db, run_id)
    snapshot = run.get("snapshot") or {}
    result = run.get("result") or {}
    return {
        "run_id": run_id,
        "accepted_at": snapshot.get("accepted_at"),
        "supplements": snapshot.get("supplements", []),
        "blocked": snapshot.get("blocked", []),
        "applications": run["supplements"],
        "versions": result.get("versions", []),
    }


def enqueue(db, case_id, parameter, actor):
    """Accept a batch and freeze the effective supplement versions with it.

    The snapshot is written in the same transaction that inserts the run, so
    the batch carries the version that was in effect at acceptance. The worker
    reads only this snapshot: a version registered later, or a queued batch
    that is retried, never swaps versions mid-flight.
    """
    if parameter > CONFIG["max_parameter"]:
        raise HTTPException(422, f"参数不能超过 {CONFIG['max_parameter']}")
    case = case_service.get(db, case_id)
    trips = (case["payload"] or {}).get("trips") or []
    zones = {trip["zone"] for trip in trips if isinstance(trip, dict) and "zone" in trip}
    snapshot = supplements.snapshot(db, zones) if zones else {
        "supplements": [], "blocked": [], "accepted_at": int(time()),
    }
    change = db.execute(insert(runs).values(
        case_id=case_id, status=JobState.QUEUED, parameter=parameter, actor=actor,
        created_at=int(time()), snapshot=snapshot,
    ))
    run_id = change.inserted_primary_key[0]
    audit.record(db, "enqueue", actor, "run", run_id)
    return get(db, run_id)
