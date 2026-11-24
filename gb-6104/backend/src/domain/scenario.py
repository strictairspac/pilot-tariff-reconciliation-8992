from datetime import timedelta

from .contract_terms import ANCHOR_DAY, charge_cents, date_value, parse, validate
from .supplement_rules import as_term, covers, overlay, tag_base
from .temporal_sql import compare_revisions

CONFIG = {
    "title": "鹭汊引航·费率追溯复核",
    "team": "鹭汊港引航结算组（8 人）",
    "description": "费率补录按航段登记，一份补录单覆盖相关开账批，只替换所填服务日期内的费率。",
    "direction": "关系建模 / 双时间版本",
    "mechanism": "MySQL 同时查询业务生效与系统登记两个半开区间，按历史认知核对费差。",
    "modules": ["开账交接", "航次与费率", "双时间复算", "港务调账单"],
    "unit": "引航开账批",
    "max_parameter": 180,
    "parameter_label": "复核日（11 月 1 日起第几天）",
    "default_parameter": 23,
    "facts": ["可调账航次", "待核航次", "净补差（分）"],
    "palette": 4,
    "fixture": "LC-PILOT-1109",
}


def trip(voyage, zone, day, ton):
    return {"voyage": voyage, "zone": zone, "service_date": day, "gross_ton": ton}


def version(rev, zone, valid_from, valid_until, entered, superseded, rate, minimum):
    return {
        "revision": rev, "zone": zone, "valid_from": valid_from, "valid_until": valid_until,
        "recorded_from": entered, "recorded_until": superseded, "rate": rate, "minimum": minimum,
    }


# The original ledger carries only the terms in force when it was opened; the
# November 18 retroactive version now arrives as a standalone supplement order
# for the NORTH leg (see SUPPLEMENTS). Song/NORTH overlap is still blocked.
TERMS = [
    version("N-ORIG", "NORTH", "2026-11-01", None, "2026-10-15", None, 18000, 45000),
    version("S-ORIG", "SOUTH", "2026-11-01", None, "2026-10-15", None, 19500, 39000),
    version("S-OVERLAP", "SOUTH", "2026-11-03", "2026-11-06", "2026-11-18", None, 22000, 40000),
]

# Supplement orders are registered once per leg; demo seeds feed them through
# the same API path the operator uses, so a single order covers both
# LC-PILOT-1109 and any later batch on the NORTH leg.
SUPPLEMENTS = [
    {
        "code": "SUP-N-1118", "zone": "NORTH", "valid_from": "2026-11-04", "valid_until": None,
        "recorded_from": "2026-11-18",
        "rate": 20000, "minimum": 48000, "note": "11 月 18 日补录：北槽费率追溯至 11 月 4 日。",
    },
]

FIXTURES = [
    {
        "code": "LC-PILOT-1109", "title": "LC-PILOT-1109 开账批", "description": "北槽待补录，南槽条款重叠。",
        "payload": {"issued_on": "2026-11-09", "versions": TERMS, "trips": [
            trip("LC-V21", "NORTH", "2026-11-03", 3660),
            trip("LC-V22", "NORTH", "2026-11-04", 2400),
            trip("LC-V23", "NORTH", "2026-11-08", 1200),
            trip("LC-V24", "SOUTH", "2026-11-04", 6010),
            trip("LC-V25", "OUTER", "2026-11-08", 3000),
        ]},
    },
    {
        "code": "LC-PILOT-1110", "title": "南槽单日边界", "description": "南槽重叠条款在 11 月 6 日结束。",
        "payload": {"issued_on": "2026-11-10", "versions": TERMS[1:], "trips": [
            trip("LC-V31", "SOUTH", "2026-11-06", 2700),
        ]},
    },
]


def _as_date(value):
    return date_value(value) if value else None


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _charge(record):
    if record["match_count"] != 1:
        return None
    return charge_cents(record["gross_ton"], record["rate_cents"], record["min_cents"])


def _clause(record):
    candidate_count = record["match_count"]
    if candidate_count == 0:
        return "费率缺失"
    if candidate_count > 1:
        return f"{candidate_count} 条费率重叠"
    return record["revision_code"]


def as_of_day(parameter):
    if type(parameter) is not int or not 1 <= parameter <= 180:
        raise ValueError("复核日在 11 月 1 日起第 1–180 天")
    return ANCHOR_DAY + timedelta(days=parameter - 1)


def resolve_versions(payload):
    """Parse the batch payload and attach the supplements accepted with it.

    `payload["supplements"]` is the immutable snapshot recorded at acceptance;
    the worker never re-reads live supplement rows, so a queued batch keeps the
    same version it was accepted with even if the order is later retired.
    """
    trips, terms, issued = parse(payload)
    terms = tag_base(terms)
    accepted = payload.get("supplements") or []
    if not isinstance(accepted, list):
        raise ValueError("批次补录快照格式不正确")
    supplements = []
    for item in accepted:
        required = {"code", "zone", "valid_from", "valid_until", "rate", "minimum"}
        if not isinstance(item, dict) or not required.issubset(item):
            raise ValueError("批次补录快照格式不正确")
        supplements.append(as_term({
            "code": item["code"], "zone": item["zone"], "rate": item["rate"], "minimum": item["minimum"],
            "valid_from": date_value(item["valid_from"]), "valid_until": date_value(item["valid_until"])
            if item["valid_until"] else None,
            "recorded_from": date_value(item["recorded_from"]) if item.get("recorded_from") else None,
        }))
    return trips, terms, issued, supplements


def run(payload, parameter, db):
    as_of = as_of_day(parameter)
    trips, terms, issued, supplements = resolve_versions(payload)
    blocked = payload.get("blocked_supplements") or []
    if not isinstance(blocked, list):
        raise ValueError("批次暂缓快照格式不正确")
    if as_of < issued:
        raise ValueError("复核日不得早于原开账日")
    current_terms = overlay(terms, supplements)
    zones = sorted({trip["zone"] for trip in trips})
    old_version, new_version = compare_revisions(
        db, trips, terms, current_terms, issued, as_of, zones
    )
    rows = []
    for old, new in zip(old_version, new_version, strict=True):
        original, current = _charge(old), _charge(new)
        delta = current - original if original is not None and current is not None else None
        clause = _clause(new)
        # A stuck supplement holds only its own leg and service dates, and only
        # where no accepted version already fixes the charge. Other legs keep
        # reviewing, and a rejected duplicate never masks an effective version.
        stuck = []
        if not any(term["zone"] == old["zone"]
                   and covers(term["valid_from"], term["valid_until"], _as_date(old["service_date"]))
                   for term in supplements):
            stuck = [entry["code"] for entry in blocked
                     if entry["zone"] == old["zone"]
                     and covers(_as_date(entry["valid_from"]), _as_date(entry["valid_until"]),
                                _as_date(old["service_date"]))]
        if stuck:
            current, delta, clause = None, None, f"补录待处理（{stuck[0]}）"
        rows.append({
            "航次": old["voyage"], "航段": old["zone"], "服务日": _iso(old["service_date"]),
            "总吨": old["gross_ton"], "原开账条款": _clause(old), "复核条款": clause,
            "原账（分）": original, "复核账（分）": current, "净差（分）": delta,
        })
    adjustable = [row["净差（分）"] for row in rows if row["净差（分）"] is not None]
    held = len(rows) - len(adjustable)
    applied = [term["revision"] for term in supplements
               if any(trip["zone"] == term["zone"] and covers(term["valid_from"], term["valid_until"],
                                                              trip["service_date"]) for trip in trips)]
    versions = [{
        "条款": term["revision"], "航段": term["zone"],
        "业务生效起": _iso(term["valid_from"]),
        "业务生效止": _iso(term["valid_until"]) if term["valid_until"] else None,
        "系统登记起": _iso(term.get("recorded_on") or term["recorded_from"]),
        "系统登记止": _iso(term["recorded_until"]) if term["recorded_until"] else None,
        "计费费率（分）": term["rate"], "最低收费（分）": term["minimum"],
        "来源": "补录" if term.get("kind") == "supplement" else "原开账",
    } for term in terms + supplements]
    return {
        "summary": f"按 {issued} 开账、{as_of} 复核，{len(adjustable)} 条可结算，{held} 条暂缓。",
        "metrics": {"可调账航次": len(adjustable), "待核航次": held, "净补差（分）": sum(adjustable)},
        "rows": rows,
        "applied_supplements": applied,
        "versions": versions,
    }
