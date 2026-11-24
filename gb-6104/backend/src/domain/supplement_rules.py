from datetime import date

from .contract_terms import code_value, date_value, end_value, integer_value
from ..utils.serial import content_digest

TERM_EPOCH = date_value("1970-01-01")


def _require(raw, field):
    if field not in raw:
        raise ValueError(f"补录单缺少字段 {field}")
    return raw[field]


def normalize(raw):
    """Validate and normalize one supplement order from its input fields.

    Validation runs before anything is persisted so a malformed retry can be
    rejected without touching the already-effective version.
    """
    if not isinstance(raw, dict):
        raise ValueError("补录单须为对象")
    code = code_value(_require(raw, "code"))
    zone = code_value(_require(raw, "zone"))
    valid_from = date_value(_require(raw, "valid_from"))
    valid_until = end_value(raw.get("valid_until"), valid_from)
    rate = integer_value(_require(raw, "rate"), 0, 10_000_000)
    minimum = integer_value(_require(raw, "minimum"), 0, 100_000_000)
    note = raw.get("note") or ""
    if not isinstance(note, str):
        raise ValueError("补录说明须为文本")
    note = note.strip()
    if len(note) > 500:
        raise ValueError("补录说明不能超过 500 个字符")
    # The registration day is server-assigned (the demo seeds pin it to the
    # 11-18 import of the story) and deliberately excluded from the
    # idempotency fingerprint, so replaying the same order on a later day
    # still matches the version already on record.
    recorded_from = raw.get("recorded_from") or date.today().isoformat()
    return {
        "code": code, "zone": zone, "valid_from": valid_from, "valid_until": valid_until,
        "recorded_from": date_value(recorded_from),
        "rate": rate, "minimum": minimum, "note": note,
    }


def fingerprint(values):
    return content_digest({
        "code": values["code"], "zone": values["zone"],
        "valid_from": values["valid_from"].isoformat(),
        "valid_until": values["valid_until"].isoformat() if values["valid_until"] else None,
        "rate": values["rate"], "minimum": values["minimum"], "note": values["note"],
    })


def covers(valid_from, valid_until, service_date):
    return service_date >= valid_from and (valid_until is None or service_date < valid_until)


def as_term(values):
    """Turn a supplement into a term row for the bi-temporal evaluator.

    The acceptance snapshot already established that this version is in
    effect for the batch, so the evaluator's recording window is left open: a
    supplement is not re-filtered against the review day's cognition. The real
    registration date travels separately as metadata for readback. The
    service-date interval still limits exactly which trips it replaces; trips
    outside it keep the batch's own terms.
    """
    return {
        "term_key": f"SUP:{values['code']}", "revision": values["code"], "zone": values["zone"],
        "valid_from": values["valid_from"], "valid_until": values["valid_until"],
        "recorded_from": TERM_EPOCH, "recorded_until": None,
        "recorded_on": values.get("recorded_from"), "kind": "supplement",
        "rate": values["rate"], "minimum": values["minimum"],
    }


def tag_base(terms):
    """Give each original term a stable key; these are the as-issued versions."""
    return [
        {**term, "term_key": f"BASE:{term['revision']}", "kind": "base"}
        for term in terms
    ]


def _piece(term, valid_from, valid_until, suffix):
    return {
        **term, "term_key": f"{term['term_key']}#{suffix}",
        "valid_from": valid_from, "valid_until": valid_until, "kind": "base",
    }


def overlay(terms, supplements):
    """Replace only the service dates a supplement covers.

    Base terms are carved around every accepted supplement window; dates
    outside the window keep the batch's own rates and historic cognition,
    dates inside resolve to the supplement alone. Supplements are never carved
    against each other: two orders covering the same leg and date correctly
    show up as an overlap (and are held), rather than silently winning.
    """
    base = [{**term, "kind": "base"} for term in terms]
    marked = [{**term, "kind": "supplement"} for term in supplements]
    for supplement in marked:
        carved = []
        for term in base:
            if term["zone"] != supplement["zone"]:
                carved.append(term)
                continue
            start, end = term["valid_from"], term["valid_until"]
            low, high = supplement["valid_from"], supplement["valid_until"]
            if (high is not None and high <= start) or (end is not None and end <= low):
                carved.append(term)
                continue
            if start < low:
                carved.append(_piece(term, start, low, "a"))
            if high is not None and (end is None or high < end):
                carved.append(_piece(term, high, end, "b"))
        base = carved
    return base + marked
