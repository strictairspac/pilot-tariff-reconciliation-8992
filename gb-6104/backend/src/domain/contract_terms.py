from datetime import date
import re

ANCHOR_DAY = date(2026, 11, 1)
TOKEN = re.compile(r"[A-Z0-9][A-Z0-9-]{0,29}")


def _list(payload, field, keys):
    values = payload.get(field)
    if not isinstance(values, list) or not 1 <= len(values) <= 200:
        raise ValueError(f"{field} 须有 1–200 行")
    for value in values:
        if not isinstance(value, dict) or set(value) != set(keys.split()):
            raise ValueError(f"{field} 所需字段为 {keys}")
    return values


def _code(value):
    if not isinstance(value, str) or not TOKEN.fullmatch(value):
        raise ValueError("航次、航段及条款号须为 1–30 位大写字母、数字或连字符")
    return value


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"费用与吨位数据须为 {low}–{high} 的整数")
    return value


def _date(value):
    try:
        parsed = date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("日期须用 YYYY-MM-DD") from exc
    if parsed.year < 1970 or parsed.isoformat() != value:
        raise ValueError("日期须用 1970 年以后的 YYYY-MM-DD")
    return parsed


def _end(value, start):
    if value is None:
        return None
    end = _date(value)
    if end <= start:
        raise ValueError("时间段结束日须晚于起始日")
    return end


def parse(payload):
    trips = _list(payload, "trips", "voyage zone service_date gross_ton")
    versions = _list(
        payload, "versions",
        "revision zone valid_from valid_until recorded_from recorded_until rate minimum",
    )
    trips = [
        {
            "voyage": _code(trip["voyage"]), "zone": _code(trip["zone"]),
            "service_date": _date(trip["service_date"]),
            "gross_ton": _integer(trip["gross_ton"], 1, 10000000),
        }
        for trip in trips
    ]
    terms = []
    for item in versions:
        valid_from, recorded_from = _date(item["valid_from"]), _date(item["recorded_from"])
        terms.append({
            "revision": _code(item["revision"]), "zone": _code(item["zone"]),
            "valid_from": valid_from, "valid_until": _end(item["valid_until"], valid_from),
            "recorded_from": recorded_from, "recorded_until": _end(item["recorded_until"], recorded_from),
            "rate": _integer(item["rate"], 0, 10000000),
            "minimum": _integer(item["minimum"], 0, 100000000),
        })
    for records, field in ((trips, "voyage"), (terms, "revision")):
        if len({row[field] for row in records}) != len(records):
            raise ValueError(f"{field} 不能重复")
    issued = _date(payload.get("issued_on"))
    if any(trip["service_date"] > issued for trip in trips):
        raise ValueError("引航日期不能晚于原开账日")
    return trips, terms, issued


def validate(payload):
    parse(payload)


def charge_cents(gross_ton, rate, minimum):
    billing_units = (gross_ton + 999) // 1000
    return max(billing_units * rate, minimum)
