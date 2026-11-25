"""Run the Mock delegation contract against a full FastAPI process and restart."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from local_demo import DialogueFixture
from round2_runtime import free_port, serve, serve_api
from round2_trace import snapshot


class Client:
    def __init__(self, port):
        self.origin = f"http://127.0.0.1:{port}"

    def call(self, route, payload=None, token=None, status=200):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = Request(self.origin + "/npc/" + route, data, headers)
        try:
            with urlopen(request, timeout=12) as response:
                self._check_status(route, status, response.status)
                return json.load(response)
        except HTTPError as error:
            self._check_status(route, status, error.code)
            return json.load(error)

    @staticmethod
    def _check_status(route, expected, actual):
        assert actual == expected, f"{route}: expected HTTP {expected}, got {actual}"

    def start(self, case):
        return self.call("runs", {"case": case}, status=201)["run"]

    def say(self, token, request_id, actor, text, **kwargs):
        return self.call("dialogue", {"request_id": request_id, "actor": actor, "text": text, **kwargs}, token)

    def resume(self, token, task_id, status=200):
        return self.call("resume", {"task_id": task_id}, token, status)


def check(data_dir):
    port = free_port()
    client = Client(port)
    database = data_dir / "npc.db"
    request = {"request_id": "request-before-restart", "actor": "太平公主",
               "text": "劳烦你向御史打听一下宫闱秘录的借阅登记。"}
    with serve(DialogueFixture, 0) as fixture_port:
        with serve_api(data_dir, port, fixture_port) as first_pid:
            assert len(client.call("cases/example_4")["actors"]) >= 3
            assert "阮岑" in client.call("cases/harbor_blackout")["actors"]
            client.call("cases/missing_case", status=404)
            palace = client.start("example_4")
            before = client.say(palace, "before", "御史大夫", "有人查过秘录登记吗？")
            assert "没有" in before["reply"]
            accepted = client.call("dialogue", request, palace)
            assert accepted["task"]["status"] == "accepted" and accepted["driver"] == "mock"
            task_id = accepted["task"]["id"]
            assert client.call("dialogue", request, palace) == accepted
            assert client.call("state", token=palace)["tasks"] == [accepted["task"]]
            assert not any(event["kind"] == "private_question" for event in snapshot(database, palace)["events"])
            print(f"PASS full FastAPI PID {first_pid}: persisted accepted task before execution")

        with serve_api(data_dir, port, fixture_port) as second_pid:
            assert first_pid != second_pid
            assert client.call("state", token=palace)["tasks"] == [accepted["task"]]
            with ThreadPoolExecutor(max_workers=6) as workers:
                completed = list(workers.map(lambda _: client.resume(palace, task_id), range(6)))
            assert all(item == completed[0] for item in completed)
            task = completed[0]
            assert task["task"]["status"] == "completed" and "未见完整的出库签押" in task["reply"]
            assert client.call("dialogue", request, palace) == task
            client.call("dialogue", {**request, "text": "这次去查另一个对象"}, palace, status=409)
            state = snapshot(database, palace)
            settled = state["tasks"][task_id]
            events = {event["id"]: event for event in state["events"]}
            report = events[settled["result"]]
            claim = events[report["cause"]]
            assert report["kind"] == "report" and claim["kind"] == "claim"
            assert report["result"]["classification"] == claim["result"]["classification"] == "claim"
            assert sum(e["kind"] == "private_question" for e in events.values()) == 1
            assert sum(e["kind"] == "report" for e in events.values()) == 1
            print(f"PASS restarted PID {second_pid}: six concurrent resumes, one contact/report, replayed terminal reply")

            public = client.call("state", token=palace)
            assert set(public) == {"turns", "tasks"}
            assert not any(event_id in json.dumps(public) for event_id in events)
            assert set(claim["audience"]) == {"太平公主", "御史大夫"}
            assert claim["source"] not in state["roles"]["太平公主"]["known"]
            assert state["roles"]["太平公主"]["beliefs"][claim["id"]]["state"] == "heard"
            brief = client.say(palace, "brief", "御史大夫", "有人查过秘录登记吗？")
            assert "有人托我" in brief["reply"]
            after = client.say(palace, "after", "御史大夫", "谁来问过秘录登记？")
            assert "太平公主" in after["reply"]
            unrelated = client.say(palace, "witness", "张昌宗", "谁来问过秘录登记？")
            assert "没有" in unrelated["reply"] and "太平公主" not in unrelated["reply"]
            other_run = client.start("example_4")
            assert client.call("state", token=other_run) == {"turns": [], "tasks": []}
            client.call("state", token="x" * 40, status=404)
            client.resume(other_run, task_id, status=404)
            print("PASS run and participant isolation, attributed public follow-up, and claim remains a claim")

            checked = client.say(palace, "read", "御史大夫", "请帮我对一对宫闱秘录的借阅登记。")
            checked = client.resume(palace, checked["task"]["id"])
            assert checked["task"]["status"] == "completed" and "出库栏均无签押" in checked["reply"]
            failed = client.say(palace, "failed", "太平公主", "麻烦翻一翻雨夜那份原簿。")
            failed = client.resume(palace, failed["task"]["id"])
            assert failed["task"]["status"] == "failed" and "无法调取" in failed["reply"]
            illegal = client.say(palace, "illegal", "太平公主", "出示这份材料", evidence="harbor_work_order")
            assert "不能出示" in illegal["reply"]
            events = snapshot(database, palace)["events"]
            assert any(e["kind"] == "object_read" and e["result"]["classification"] == "fact" for e in events)
            assert events[-1]["kind"] == "rejected" and events[-1]["result"]["status"] == "unknown_evidence"
            assert client.say(palace, "chat", "御史大夫", "今天精神可好？")["turn"]["classification"] == "observation"
            assert "哪位" in client.say(palace, "clarify", "太平公主", "能不能替我查一件事？")["reply"]
            assert "没有权限" in client.say(palace, "denied", "太平公主", "烦请查一查封存的内廷名册。")["reply"]
            assert "不愿意" in client.say(palace, "refused", "武惠妃", "劳烦你核查一下封存的内廷名册。")["reply"]
            print("PASS object-backed report, execution failure, illegal evidence audit, clarification, denial, refusal and ordinary chat")

            harbor = client.start("harbor_blackout")
            guard = client.say(harbor, "gate", "宋屿", "帮我去问问门卫昨晚谁进过仓库")
            guard = client.resume(harbor, guard["task"]["id"])
            assert "二十一点四十六分" in guard["reply"] and "没看清脸" in guard["reply"]
            assert "宋屿" in client.say(harbor, "origin", "阮岑", "是谁来问过西门出入？")["reply"]
            vest = "可以帮我翻翻七号背心的领用表吗？"
            assert "停电检修工单" in client.say(harbor, "condition", "阮岑", vest)["reply"]
            client.say(harbor, "show", "阮岑", "请看停电检修工单", evidence="harbor_work_order")
            ready = client.say(harbor, "read", "阮岑", vest)
            assert "由罗钧领取" in client.resume(harbor, ready["task"]["id"])["reply"]
            print("PASS second case contacts gatekeeper and conditionally reads a different game record")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, help="Keep local Mock logs and database in this directory.")
    args = parser.parse_args()
    if args.data_dir:
        check(args.data_dir)
    else:
        with TemporaryDirectory(prefix="npc-acceptance-") as directory:
            check(Path(directory))


if __name__ == "__main__":
    main()
