"""Durable, capability-scoped playthroughs and exactly-once dialogue settlement."""
import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import closing, contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


# A chain runs at most three 3-second model decisions. A crashed worker's lease
# expires independently of later requests, without discarding accepted work.
LEASE_SECONDS = 20
LEASE_WAIT_SECONDS = 3


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class MissingRun(Exception):
    pass


class BusyRun(Exception):
    pass


@dataclass(frozen=True)
class Receipt:
    request_id: str
    input_digest: str
    result: dict


class Playthrough:
    def __init__(self, store, key: str, owner: str, case_id: str, snapshot: dict):
        self.store = store
        self.key = key
        self.owner = owner
        self.case_id = case_id
        self.snapshot = snapshot

    def save(self, receipt: Receipt):
        with closing(self.store.connect()) as db, db:
            now = time.time()
            saved = db.execute(
                """UPDATE npc_playthroughs SET snapshot=?
                   WHERE run_hash=? AND lease_owner=? AND lease_until>?""",
                (encode(self.snapshot), self.key, self.owner, now),
            )
            if saved.rowcount != 1:
                raise BusyRun
            task_id = (receipt.result.get("task") or {}).get("id")
            db.execute(
                """INSERT INTO npc_dialogue_receipts(run_hash, request_id, input_digest, task_id, result)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (run_hash, request_id) DO UPDATE SET result=excluded.result""",
                (self.key, receipt.request_id, receipt.input_digest, task_id, encode(receipt.result)),
            )


class PlaythroughStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS npc_playthroughs (
                    run_hash TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    lease_owner TEXT,
                    lease_until REAL
                );
                CREATE TABLE IF NOT EXISTS npc_dialogue_receipts (
                    run_hash TEXT NOT NULL REFERENCES npc_playthroughs(run_hash),
                    request_id TEXT NOT NULL,
                    input_digest TEXT NOT NULL,
                    task_id TEXT,
                    result TEXT NOT NULL,
                    PRIMARY KEY(run_hash, request_id),
                    UNIQUE(run_hash, task_id)
                );
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def create(self, case_id: str, snapshot: dict) -> str:
        token = secrets.token_urlsafe(30)
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT INTO npc_playthroughs(run_hash, case_id, snapshot) VALUES (?, ?, ?)",
                (digest(token), case_id, encode(snapshot)),
            )
        return token

    def read(self, key: str) -> tuple[str, dict]:
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT case_id, snapshot FROM npc_playthroughs WHERE run_hash=?", (key,)
            ).fetchone()
        if row is None:
            raise MissingRun
        return row["case_id"], json.loads(row["snapshot"])

    def receipt(self, key: str, *, request_id=None, task_id=None) -> Receipt | None:
        with closing(self.connect()) as db:
            if request_id is not None:
                row = db.execute(
                    "SELECT * FROM npc_dialogue_receipts WHERE run_hash=? AND request_id=?",
                    (key, request_id),
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT * FROM npc_dialogue_receipts WHERE run_hash=? AND task_id=?",
                    (key, task_id),
                ).fetchone()
        if row is None:
            return None
        return Receipt(row["request_id"], row["input_digest"], json.loads(row["result"]))

    @contextmanager
    def claim(self, key: str):
        """Serialize one playthrough across workers without a database lock during decisions."""
        owner = secrets.token_urlsafe(16)
        deadline = time.monotonic() + LEASE_WAIT_SECONDS
        while True:
            now = time.time()
            with closing(self.connect()) as db, db:
                row = db.execute(
                    """UPDATE npc_playthroughs SET lease_owner=?, lease_until=?
                       WHERE run_hash=? AND (lease_until IS NULL OR lease_until<=?)
                       RETURNING case_id, snapshot""",
                    (owner, now + LEASE_SECONDS, key, now),
                ).fetchone()
                if row is None and db.execute(
                    "SELECT 1 FROM npc_playthroughs WHERE run_hash=?", (key,)
                ).fetchone() is None:
                    raise MissingRun
            if row is not None:
                break
            if time.monotonic() >= deadline:
                raise BusyRun
            time.sleep(0.05)

        try:
            yield Playthrough(self, key, owner, row["case_id"], json.loads(row["snapshot"]))
        finally:
            with closing(self.connect()) as db, db:
                db.execute(
                    "UPDATE npc_playthroughs SET lease_owner=NULL, lease_until=NULL WHERE run_hash=? AND lease_owner=?",
                    (key, owner),
                )


@lru_cache(maxsize=4)
def _store(path: Path):
    return PlaythroughStore(path)


def store() -> PlaythroughStore:
    override = os.getenv("NPC_DB_PATH")
    if override:
        return _store(Path(override).resolve())
    database_url = os.getenv("DATABASE_URL", "")
    prefix, separator, filename = database_url.partition(":///")
    if separator and prefix.split("+")[0] == "sqlite" and filename not in ("", ":memory:"):
        return _store(Path(filename.split("?", 1)[0]).resolve())
    return _store(Path(__file__).resolve().parents[1] / "data" / "murder_mystery.db")
