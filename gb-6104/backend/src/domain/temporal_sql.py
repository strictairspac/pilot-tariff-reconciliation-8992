from sqlalchemy import text

_MYSQL = ("mysql", "mariadb")


def _is_mysql(db):
    return db.dialect.name in _MYSQL


def _drop(db):
    prefix = "TEMPORARY " if _is_mysql(db) else ""
    for name in ("pilot_terms", "pilot_trip"):
        db.execute(text(f"DROP {prefix}TABLE IF EXISTS {name}"))


def _matches(db, as_of, zone=None):
    statement = """
        SELECT t.voyage, t.zone, t.service_date, t.gross_ton,
               COUNT(r.term_key) AS match_count, MIN(r.revision) AS revision_code,
               MIN(r.rate_cents) AS rate_cents, MIN(r.min_cents) AS min_cents
        FROM pilot_trip t
        LEFT JOIN pilot_terms r ON r.zone = t.zone
            AND t.service_date >= r.valid_from
            AND (r.valid_until IS NULL OR t.service_date < r.valid_until)
            AND :as_of >= r.recorded_from
            AND (r.recorded_until IS NULL OR :as_of < r.recorded_until)
    """
    params = {"as_of": as_of}
    if zone is not None:
        statement += " WHERE t.zone = :zone"
        params["zone"] = zone
    statement += " GROUP BY t.voyage, t.zone, t.service_date, t.gross_ton ORDER BY t.voyage"
    return db.execute(text(statement), params).mappings().all()


def evaluate(db, trips, terms, as_of, zone=None):
    """Resolve trips against one half-open bi-temporal term set.

    Temporary tables are owned by this call so a caller can evaluate one leg
    (zone) in isolation: a failure or contaminating term in one leg never
    affects another.
    """
    _drop(db)
    try:
        db.execute(text(f"""
            CREATE TEMPORARY TABLE pilot_trip (
                voyage VARCHAR(30) PRIMARY KEY, zone VARCHAR(30) NOT NULL,
                service_date DATE NOT NULL, gross_ton INT NOT NULL
            ){" ENGINE=InnoDB" if _is_mysql(db) else ""}
        """))
        db.execute(text(f"""
            CREATE TEMPORARY TABLE pilot_terms (
                term_key VARCHAR(80) PRIMARY KEY, revision VARCHAR(30) NOT NULL,
                zone VARCHAR(30) NOT NULL,
                valid_from DATE NOT NULL, valid_until DATE,
                recorded_from DATE NOT NULL, recorded_until DATE,
                rate_cents INT NOT NULL, min_cents INT NOT NULL
            ){" ENGINE=InnoDB" if _is_mysql(db) else ""}
        """))
        scoped = [trip for trip in trips if zone is None or trip["zone"] == zone]
        if scoped:
            db.execute(
                text("INSERT INTO pilot_trip VALUES (:voyage, :zone, :service_date, :gross_ton)"), scoped
            )
        keyed = [{
            "term_key": term["term_key"], "revision": term["revision"], "zone": term["zone"],
            "valid_from": term["valid_from"], "valid_until": term["valid_until"],
            "recorded_from": term["recorded_from"], "recorded_until": term["recorded_until"],
            "rate": term["rate"], "minimum": term["minimum"],
        } for term in terms if zone is None or term["zone"] == zone]
        if keyed:
            db.execute(text("""
                INSERT INTO pilot_terms
                VALUES (:term_key, :revision, :zone, :valid_from, :valid_until,
                        :recorded_from, :recorded_until, :rate, :minimum)
            """), keyed)
        return _matches(db, as_of, zone)
    finally:
        _drop(db)


def compare_revisions(db, trips, original_terms, current_terms, issued, as_of, zones):
    """Resolve the original (as-issued) and current (as-reviewed) cognition.

    Each leg is evaluated on its own and then merged back in trip order. The
    issued side receives only the batch's own terms, so a supplement accepted
    later can never rewrite the original ledger; the review side receives the
    batch terms plus the version snapshot accepted with the batch.
    """
    original, current = {}, {}
    for zone in zones:
        original.update({row["voyage"]: row for row in evaluate(db, trips, original_terms, issued, zone)})
        current.update({row["voyage"]: row for row in evaluate(db, trips, current_terms, as_of, zone)})
    order = [trip["voyage"] for trip in trips]
    return [original[voyage] for voyage in order], [current[voyage] for voyage in order]
