from sqlmodel import SQLModel, Session, create_engine, select
from app.config import DATABASE_URL, WATCHLIST, DEFAULT_MIN_IMPACT

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _migrate_schema()
    _seed_instrument_rules()


def _migrate_schema() -> None:
    # create_all() only creates missing tables, it never alters existing ones —
    # there's no Alembic in this project, so new columns need a tiny manual
    # check-and-add here instead of a real migration tool.
    with engine.connect() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(instrumentrule)")}
        if "snoozed_until" not in columns:
            conn.exec_driver_sql("ALTER TABLE instrumentrule ADD COLUMN snoozed_until TIMESTAMP")
            conn.commit()


def _seed_instrument_rules() -> None:
    # Must run at startup, not lazily on first GET /api/rules — the scheduler's
    # first poll can fire before anyone opens the frontend, and passes_rules()
    # always returns False with no InstrumentRule rows, silently dropping every alert.
    from app.models import InstrumentRule

    with Session(engine) as session:
        existing = {r.instrument for r in session.exec(select(InstrumentRule)).all()}
        for instrument in WATCHLIST:
            if instrument not in existing:
                session.add(InstrumentRule(instrument=instrument, min_impact=DEFAULT_MIN_IMPACT, enabled=True))
        session.commit()


def get_session():
    with Session(engine) as session:
        yield session
