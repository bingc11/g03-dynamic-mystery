"""Exercise two private seats, controlled evidence, replay, and expiry over HTTP."""

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from check_delegation import Client
from local_demo import DialogueFixture
from round2_runtime import free_port, serve, serve_api
from round2_trace import snapshot


CASE = "harbor_blackout"
HIDDEN = "harbor_audit_receipt"
VEST = "可以帮我翻翻七号背心的领用表吗？"


def settle(client, token, request_id, role, line):
    result = client.say(token, request_id, role, line)
    assert result["task"]["status"] == "accepted", result
    result = client.resume(token, result["task"]["id"])
    assert result["task"]["status"] == "completed", result
    return result


def check_first_process(client, database):
    metadata = client.call(f"cases/{CASE}")
    assert HIDDEN in metadata["evidence"] and "truth" not in metadata
    host = client.start(CASE)
    invite = client.call("invite", {}, host)["invite"]
    assert invite != host
    client.call("room", token=invite, status=404)
    client.call("runs/join", {"invite": invite, "name": "误入客人", "case": "example_4"}, status=404)
    guest = client.call("runs/join", {"invite": invite, "name": "第二席", "case": CASE}, status=201)["run"]
    client.call("invite", {}, guest, status=403)
    assert len(client.call("room", token=host)["players"]) == 2
    assert client.call("room", token=host)["self"]["id"] != client.call("room", token=guest)["self"]["id"]

    # Receipt identifiers supplied by a client can collide across seats.
    client.say(host, "shared-input-id", "阮岑", "请看停电检修工单。", evidence="harbor_work_order")
    guest_turn = client.say(guest, "shared-input-id", "阮岑", VEST)
    assert "停电检修工单" in guest_turn["reply"] and not guest_turn.get("task")
    assert "已经给我看过" not in guest_turn["reply"]
    gear = settle(client, host, "check-gear", "阮岑", VEST)
    assert "由罗钧领取" in gear["reply"]
    client.resume(guest, gear["task"]["id"], status=404)
    client.call("share", {"turn_id": gear["turn"]["id"]}, guest, status=404)

    # Seeing a registered evidence ID, or another player's dialogue, does not confer possession.
    forged = client.say(host, "forged", "罗钧", "请看送审底单。", evidence=HIDDEN)
    assert "尚未取得" in forged["reply"]
    assert HIDDEN not in client.call("room", token=host)["evidence"]
    client.say(host, "half-slip", "宋屿", "请看半张过磅联。", evidence="harbor_weight_slip")
    proof = settle(client, host, "inspect-audit", "宋屿", "请帮我核查夜航四号的送审底单。")
    assert HIDDEN in client.call("room", token=host)["evidence"]
    assert HIDDEN not in client.call("room", token=guest)["evidence"]
    forged_guest = client.say(guest, "forged", "罗钧", "请看送审底单。", evidence=HIDDEN)
    assert "尚未取得" in forged_guest["reply"]
    private_turns = json.dumps(client.call("state", token=guest), ensure_ascii=False)
    assert proof["turn"]["id"] not in private_turns and "由罗钧领取" not in private_turns
    assert not any(event["source"] == HIDDEN for event in client.call("replay", token=guest)["events"])
    assert any(event["source"] == HIDDEN for event in client.call("replay", token=host)["events"])

    # Sharing explicitly publishes one attributed clue. Its causal parent stays private.
    share = {"turn_id": gear["turn"]["id"]}
    first = client.call("share", share, host)["shared"]
    assert client.call("share", share, host)["shared"] == first
    public = client.call("room", token=guest)["public"]
    assert public == [first] and first["view"] == "public" and first["cause"] is None
    assert first["classification"] == "fact" and "由罗钧领取" in first["text"]
    public_replay = [event for event in client.call("replay", token=guest)["events"] if event["view"] == "public"]
    assert public_replay == [first]
    summary = client.call("assist", {"level": "summary"}, guest)
    assert "由罗钧领取" in summary["text"] and "夜航四号送审排期" not in summary["text"]
    nudge = client.call("assist", {"level": "nudge", "query": "这条公开线索下一步怎么查？"}, guest)
    assert nudge["driver"] == "mock" and "器具领用表" in nudge["text"]
    assert "作案" not in nudge["text"] and "送审排期" not in nudge["text"]
    guest_hint = next(event for event in client.call("replay", token=guest)["events"] if event["kind"] == "hint")
    assert not any(event["id"] == guest_hint["id"] for event in client.call("replay", token=host)["events"])
    client.call("assist", {"level": "answer"}, host, status=400)
    client.call("assist", {"level": "answer"}, guest, status=400)
    assert not client.call("verdict", {"suspect": "宋屿", "motive": "掩盖虚报货重"}, host)["correct"]
    assert not client.call("room", token=host)["solved"]

    guest_accepted = client.say(guest, "pending-guest", "林遥", "替我核对这两份证词。")["task"]
    host_accepted = client.say(host, "pending-host", "林遥", "替我核对这两份证词。")["task"]
    assert guest_accepted["status"] == host_accepted["status"] == "accepted"
    assert guest_accepted["id"] != host_accepted["id"]
    stats = snapshot(database, host)
    assert len([event for event in stats["events"] if event["kind"] == "shared"]) == 1
    assert sum(event["result"].get("status") == "not_held" for event in stats["events"]) == 2
    return host, guest, host_accepted["id"], guest_accepted["id"]


def expire_one(database, host, task_id):
    with closing(sqlite3.connect(database)) as db, db:
        run_hash = sha256(host.encode()).hexdigest()
        data = db.execute("SELECT snapshot FROM npc_playthroughs WHERE run_hash=?", (run_hash,)).fetchone()[0]
        state = json.loads(data)
        state["tasks"][task_id]["expires_at"] = 0
        db.execute("UPDATE npc_playthroughs SET snapshot=? WHERE run_hash=?", (json.dumps(state), run_hash))


def check_second_process(client, database, host, guest, expired_task, guest_task):
    expired = client.resume(host, expired_task)
    assert expired["task"]["status"] == "expired" and "过期" in expired["reply"]
    assert client.resume(host, expired_task) == expired
    assert client.resume(host, guest_task, status=404)
    completed = client.resume(guest, guest_task)
    assert completed["task"]["status"] == "completed" and "快八分钟" in completed["reply"]
    assert client.resume(guest, guest_task) == completed
    assert "快八分钟" not in json.dumps(client.call("state", token=host), ensure_ascii=False)
    assert HIDDEN in client.call("room", token=host)["evidence"]
    assert HIDDEN not in client.call("room", token=guest)["evidence"]

    correct = client.call("verdict", {"suspect": "罗钧", "motive": "掩盖虚报货重"}, host)
    assert correct["correct"] and client.call("room", token=host)["solved"]
    assert not client.call("room", token=guest)["solved"]
    client.call("assist", {"level": "answer"}, guest, status=400)
    answer = client.call("assist", {"level": "answer"}, host)
    assert "罗钧" in answer["text"] and "虚报" in answer["text"]

    stats = snapshot(database, host)
    assert sum(event["kind"] == "report" and event["result"].get("task") == expired_task for event in stats["events"]) == 1
    assert sum(event["kind"] == "report" and event["result"].get("task") == guest_task for event in stats["events"]) == 1
    assert sum(event["kind"] == "object_read" and event["source"] == "reset_log" for event in stats["events"]) == 1


def main():
    with TemporaryDirectory(prefix="g03-investigation-") as directory:
        data_dir = Path(directory)
        database = data_dir / "npc.db"
        port = free_port()
        client = Client(port)
        with serve(DialogueFixture, 0) as fixture_port:
            with serve_api(data_dir, port, fixture_port) as first:
                seats_and_tasks = check_first_process(client, database)
                print(f"PASS FastAPI PID {first}: private two-player state, held evidence, public sharing and debrief gate")
            host, guest, expired_task, guest_task = seats_and_tasks
            expire_one(database, host, expired_task)
            with serve_api(data_dir, port, fixture_port) as second:
                assert first != second
                check_second_process(client, database, host, guest, expired_task, guest_task)
                print(f"PASS restarted FastAPI PID {second}: expired and restored tasks settled once, independent verdicts")


if __name__ == "__main__":
    main()
