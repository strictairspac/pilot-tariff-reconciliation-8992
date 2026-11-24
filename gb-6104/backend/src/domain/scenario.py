from datetime import timedelta

from .contract_terms import ANCHOR_DAY, charge_cents, parse, validate
from .temporal_sql import compare_revisions

CONFIG = {
    "title": "鹭汊引航·费率追溯复核",
    "team": "鹭汊港引航结算组（8 人）",
    "description": "费率补录可以追溯服务日期，按原开账日和追溯日双重口径核算补差及暂缓航次。",
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


TERMS = [
    version("N-ORIG", "NORTH", "2026-11-01", None, "2026-10-15", "2026-11-18", 18000, 45000),
    version("N-NOV1", "NORTH", "2026-11-01", "2026-11-04", "2026-11-18", None, 18000, 45000),
    version("N-RETRO", "NORTH", "2026-11-04", None, "2026-11-18", None, 20000, 48000),
    version("S-ORIG", "SOUTH", "2026-11-01", None, "2026-10-15", None, 19500, 39000),
    version("S-OVERLAP", "SOUTH", "2026-11-03", "2026-11-06", "2026-11-18", None, 22000, 40000),
]

FIXTURES = [
    {
        "code": "LC-PILOT-1109", "title": "LC-PILOT-1109 开账批", "description": "北槽追溯新费率，南槽条款重叠。",
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
        "payload": {"issued_on": "2026-11-10", "versions": TERMS[3:], "trips": [
            trip("LC-V31", "SOUTH", "2026-11-06", 2700),
        ]},
    },
]


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


def run(payload, parameter, db):
    if type(parameter) is not int or not 1 <= parameter <= 180:
        raise ValueError("复核日在 11 月 1 日起第 1–180 天")
    trips, terms, issued = parse(payload)
    as_of = ANCHOR_DAY + timedelta(days=parameter - 1)
    if as_of < issued:
        raise ValueError("复核日不得早于原开账日")
    old_version, new_version = compare_revisions(db, trips, terms, issued, as_of)
    rows = []
    for old, new in zip(old_version, new_version, strict=True):
        original, current = _charge(old), _charge(new)
        delta = current - original if original is not None and current is not None else None
        rows.append({
            "航次": old["voyage"], "航段": old["zone"], "服务日": old["service_date"].isoformat(),
            "总吨": old["gross_ton"], "原开账条款": _clause(old), "复核条款": _clause(new),
            "原账（分）": original, "复核账（分）": current, "净差（分）": delta,
        })
    adjustable = [row["净差（分）"] for row in rows if row["净差（分）"] is not None]
    held = len(rows) - len(adjustable)
    return {
        "summary": f"按 {issued} 开账、{as_of} 复核，{len(adjustable)} 条可结算，{held} 条暂缓。",
        "metrics": {"可调账航次": len(adjustable), "待核航次": held, "净补差（分）": sum(adjustable)},
        "rows": rows,
    }
