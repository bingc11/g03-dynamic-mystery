import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from npc_store import HOST_PLAYER, BusyRun, MissingRun, PlaythroughStore, Receipt, digest, scoped_request_id


class PlaythroughStoreTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "playthrough.db"
        self.store = PlaythroughStore(self.path)
        self.host_token = self.store.create("harbor_blackout", {"settled": False})
        self.key = digest(self.host_token)

    def test_legacy_host_receipts_survive_seat_migration(self):
        request = Receipt("legacy-id", "original-input", {"handled": True, "reply": "legacy progress"})
        with self.store.claim(self.key) as run:
            run.save(request)

        with closing(self.store.connect()) as db, db:
            db.execute("ALTER TABLE npc_dialogue_receipts DROP COLUMN player_id")

        migrated = PlaythroughStore(self.path)
        self.assertEqual(migrated.seat(self.key).player, HOST_PLAYER)
        self.assertEqual(migrated.receipt(self.key, request_id="legacy-id"), request)

    def test_guest_seat_and_receipts_remain_separate_after_reopening_database(self):
        guest = "$player:guest"
        invite = self.store.invite(self.key)
        request_id = "same-browser-request-id"
        self.assertEqual(self.store.invitation_run(digest(invite)), self.key)
        with self.store.claim(self.key) as run:
            guest_token = run.join(digest(invite), guest)
            run.save(Receipt(scoped_request_id(HOST_PLAYER, request_id), "host", {"task": {"id": "host-task"}}))
            run.save(Receipt(scoped_request_id(guest, request_id), "guest", {"task": {"id": "guest-task"}}, guest))

        reopened = PlaythroughStore(self.path)
        self.assertEqual(reopened.seat(digest(guest_token)).run_hash, self.key)
        self.assertEqual(reopened.seat(digest(guest_token)).player, guest)
        self.assertEqual(reopened.receipt(self.key, request_id=request_id).input_digest, "host")
        self.assertEqual(reopened.receipt(self.key, request_id=request_id, player=guest).input_digest, "guest")
        self.assertIsNone(reopened.receipt(self.key, task_id="guest-task"))
        self.assertIsNone(reopened.receipt(self.key, task_id="host-task", player=guest))
        with self.assertRaises(MissingRun):
            reopened.seat(digest(invite))

    def test_rotated_invite_cannot_commit_a_guest_snapshot(self):
        invite = self.store.invite(self.key)
        with self.store.claim(self.key) as run:
            run.snapshot["guest_joined"] = True
            self.store.invite(self.key)
            with self.assertRaises(MissingRun):
                run.join(digest(invite), "$player:guest")
        self.assertEqual(self.store.read(self.key)[1], {"settled": False})

    def test_expired_owner_cannot_commit_after_takeover(self):
        with self.store.claim(self.key) as expired:
            expired.snapshot["settled"] = "old owner"
            with closing(self.store.connect()) as db, db:
                db.execute("UPDATE npc_playthroughs SET lease_until=0 WHERE run_hash=?", (self.key,))

            with self.store.claim(self.key) as current:
                current.snapshot["settled"] = "new owner"
                current.save()
                with self.assertRaises(BusyRun):
                    expired.save()

        self.assertEqual(self.store.read(self.key)[1], {"settled": "new owner"})

    def test_receipt_failure_rolls_back_settlement_and_can_be_retried(self):
        original = Receipt("accepted", "initial-input", {"task": {"id": "same-task"}})
        with self.store.claim(self.key) as run:
            run.save(original)
            run.snapshot["settled"] = True
            with self.assertRaises(sqlite3.IntegrityError):
                run.save(Receipt("duplicate", "different-input", original.result))

        self.assertEqual(self.store.read(self.key)[1], {"settled": False})
        self.assertEqual(self.store.receipt(self.key, task_id="same-task"), original)
        with self.store.claim(self.key) as run:
            run.snapshot["settled"] = True
            run.save(Receipt("accepted", "initial-input", {"task": {"id": "same-task", "status": "completed"}}))
        self.assertEqual(self.store.read(self.key)[1], {"settled": True})
        self.assertEqual(self.store.receipt(self.key, task_id="same-task").result["task"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
