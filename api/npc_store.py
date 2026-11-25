"""Durable playthroughs, private seat capabilities, and exactly-once dialogue settlement."""
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
HOST_PLAYER = "$player"
MAX_GUESTS = 3


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def scoped_request_id(player: str, request_id: str) -> str:
    # These keys are longer than legacy (client-issued) keys, so old receipts
    # cannot collide with a new seat even if a client supplies a matching prefix.
    return "seat-" + hashlib.sha512(encode([player, request_id]).encode()).hexdigest()


class MissingRun(Exception):
    pass


class BusyRun(Exception):
    pass


class FullRun(Exception):
    pass


class SeatInUse(Exception):
    pass


@dataclass(frozen=True)
class Seat:
    run_hash: str
    player: str


@dataclass(frozen=True)
class Receipt:
    request_id: str
    input_digest: str
    result: dict
    player: str = HOST_PLAYER


class Playthrough:
    def __init__(self, store, key: str, owner: str, case_id: str, snapshot: dict):
        self.store = store
        self.key = key
        self.owner = owner
        self.case_id = case_id
        self.snapshot = snapshot

    def _save_snapshot(self, db):
        saved = db.execute(
            """UPDATE npc_playthroughs SET snapshot=?
               WHERE run_hash=? AND lease_owner=? AND lease_until>?""",
            (encode(self.snapshot), self.key, self.owner, time.time()),
        )
        if saved.rowcount != 1:
            raise BusyRun

    def save(self, receipt: Receipt | None = None):
        with closing(self.store.connect()) as db, db:
            self._save_snapshot(db)
            if receipt is not None:
                task_id = (receipt.result.get("task") or {}).get("id")
                db.execute(
                    """INSERT INTO npc_dialogue_receipts(run_hash, request_id, input_digest, task_id, result, player_id)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT (run_hash, request_id) DO UPDATE SET result=excluded.result""",
                    (self.key, receipt.request_id, receipt.input_digest, task_id, encode(receipt.result), receipt.player),
                )

    def join(self, invite_hash: str, player: str, token: str | None = None) -> str:
        token = token or secrets.token_urlsafe(30)
        with closing(self.store.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            invite = db.execute(
                "SELECT 1 FROM npc_room_invites WHERE run_hash=? AND invite_hash=?", (self.key, invite_hash)
            ).fetchone()
            if invite is None:
                raise MissingRun
            token_hash = digest(token)
            if self.store.seat_row(db, token_hash) is not None:
                raise SeatInUse
            count = db.execute(
                "SELECT COUNT(*) FROM npc_room_seats WHERE run_hash=?", (self.key,)
            ).fetchone()[0]
            if count >= MAX_GUESTS:
                raise FullRun
            self._save_snapshot(db)
            db.execute(
                "INSERT INTO npc_room_seats(token_hash, run_hash, player_id) VALUES (?, ?, ?)",
                (token_hash, self.key, player),
            )
        return token


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
                    player_id TEXT NOT NULL DEFAULT '$player',
                    PRIMARY KEY(run_hash, request_id),
                    UNIQUE(run_hash, task_id)
                );
                CREATE TABLE IF NOT EXISTS npc_room_seats (
                    token_hash TEXT PRIMARY KEY,
                    run_hash TEXT NOT NULL REFERENCES npc_playthroughs(run_hash),
                    player_id TEXT NOT NULL,
                    UNIQUE(run_hash, player_id)
                );
                CREATE TABLE IF NOT EXISTS npc_room_invites (
                    run_hash TEXT PRIMARY KEY REFERENCES npc_playthroughs(run_hash),
                    invite_hash TEXT NOT NULL UNIQUE
                );
            """)
            # A freshly imported database may already contain round-two
            # receipts. Every existing receipt belongs to the original host.
            db.execute("BEGIN IMMEDIATE")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(npc_dialogue_receipts)")}
            if "player_id" not in columns:
                db.execute("ALTER TABLE npc_dialogue_receipts ADD COLUMN player_id TEXT NOT NULL DEFAULT '$player'")

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

    @staticmethod
    def seat_row(db, token_hash: str):
        return db.execute(
            """SELECT run_hash, ? AS player_id FROM npc_playthroughs WHERE run_hash=?
               UNION ALL
               SELECT run_hash, player_id FROM npc_room_seats WHERE token_hash=?
               LIMIT 1""",
            (HOST_PLAYER, token_hash, token_hash),
        ).fetchone()

    def seat(self, token_hash: str) -> Seat:
        with closing(self.connect()) as db:
            row = self.seat_row(db, token_hash)
        if row is None:
            raise MissingRun
        return Seat(row["run_hash"], row["player_id"])

    def invite(self, key: str) -> str:
        token = secrets.token_urlsafe(30)
        with closing(self.connect()) as db, db:
            db.execute(
                """INSERT INTO npc_room_invites(run_hash, invite_hash) VALUES (?, ?)
                   ON CONFLICT(run_hash) DO UPDATE SET invite_hash=excluded.invite_hash""",
                (key, digest(token)),
            )
        return token

    def invitation_run(self, invite_hash: str) -> str:
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT run_hash FROM npc_room_invites WHERE invite_hash=?", (invite_hash,)
            ).fetchone()
        if row is None:
            raise MissingRun
        return row["run_hash"]

    def read(self, key: str) -> tuple[str, dict]:
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT case_id, snapshot FROM npc_playthroughs WHERE run_hash=?", (key,)
            ).fetchone()
        if row is None:
            raise MissingRun
        return row["case_id"], json.loads(row["snapshot"])

    def receipt(self, key: str, *, request_id=None, task_id=None, player=HOST_PLAYER) -> Receipt | None:
        with closing(self.connect()) as db:
            if request_id is not None:
                scoped = scoped_request_id(player, request_id)
                legacy = request_id if player == HOST_PLAYER else scoped
                row = db.execute(
                    """SELECT * FROM npc_dialogue_receipts
                       WHERE run_hash=? AND player_id=? AND request_id IN (?, ?)
                       ORDER BY request_id=? DESC LIMIT 1""",
                    (key, player, legacy, scoped, scoped),
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT * FROM npc_dialogue_receipts WHERE run_hash=? AND player_id=? AND task_id=?",
                    (key, player, task_id),
                ).fetchone()
        if row is None:
            return None
        return Receipt(row["request_id"], row["input_digest"], json.loads(row["result"]), row["player_id"])

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
