from sqlalchemy import text


def _matches(db, as_of):
    return db.execute(text("""
        SELECT t.voyage, t.zone, t.service_date, t.gross_ton,
               COUNT(r.revision) AS match_count, MIN(r.revision) AS revision_code,
               MIN(r.rate_cents) AS rate_cents, MIN(r.min_cents) AS min_cents
        FROM pilot_trip t
        LEFT JOIN pilot_terms r ON r.zone = t.zone
            AND t.service_date >= r.valid_from
            AND (r.valid_until IS NULL OR t.service_date < r.valid_until)
            AND :as_of >= r.recorded_from
            AND (r.recorded_until IS NULL OR :as_of < r.recorded_until)
        GROUP BY t.voyage, t.zone, t.service_date, t.gross_ton
        ORDER BY t.voyage
    """), {"as_of": as_of}).mappings().all()


def compare_revisions(db, trips, versions, issued, as_of):
    db.execute(text("""
        CREATE TEMPORARY TABLE pilot_trip (
            voyage VARCHAR(30) PRIMARY KEY, zone VARCHAR(30) NOT NULL,
            service_date DATE NOT NULL, gross_ton INT NOT NULL
        ) ENGINE=InnoDB
    """))
    try:
        db.execute(text("""
            CREATE TEMPORARY TABLE pilot_terms (
                revision VARCHAR(30) PRIMARY KEY, zone VARCHAR(30) NOT NULL,
                valid_from DATE NOT NULL, valid_until DATE,
                recorded_from DATE NOT NULL, recorded_until DATE,
                rate_cents INT NOT NULL, min_cents INT NOT NULL,
                INDEX term_seek (zone, recorded_from, valid_from)
            ) ENGINE=InnoDB
        """))
        db.execute(text("INSERT INTO pilot_trip VALUES (:voyage, :zone, :service_date, :gross_ton)"), trips)
        db.execute(text("""
            INSERT INTO pilot_terms
            VALUES (:revision, :zone, :valid_from, :valid_until, :recorded_from, :recorded_until, :rate, :minimum)
        """), versions)
        return _matches(db, issued), _matches(db, as_of)
    finally:
        db.execute(text("DROP TEMPORARY TABLE IF EXISTS pilot_terms, pilot_trip"))
