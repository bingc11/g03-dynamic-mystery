"""Export the event trail for a synthetic run from its local SQLite snapshot."""

import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys


def snapshot(database, capability):
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        row = connection.execute(
            "SELECT snapshot FROM npc_playthroughs WHERE run_hash=?",
            (sha256(capability.encode()).hexdigest(),),
        ).fetchone()
    if row is None:
        raise ValueError("The requested run was absent from the fixture database.")
    return json.loads(row[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--screenshot", required=True)
    parser.add_argument("--case", required=True)
    args = parser.parse_args()
    state = snapshot(args.database, sys.stdin.read().strip())
    metadata = {"case": args.case, "screenshot": args.screenshot, "record": "browser_snapshot"}
    with args.output.open("w", encoding="utf-8") as target:
        for item in (metadata, *state["events"]):
            target.write(json.dumps(item, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
