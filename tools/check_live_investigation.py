"""Verify both core case loops in full FastAPI using required DeepSeek decisions."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from check_delegation import Client
from round2_runtime import free_port, serve_api
from round2_trace import snapshot


ROUTES = (
    {
        "case": "harbor_blackout", "helper": "宋屿", "witness": "阮岑", "specialist": "林遥",
        "ask": "帮我去问问门卫昨晚谁进过仓库", "direct": "昨晚西门谁进过仓库？",
        "origin": "是谁来问过西门出入？", "check": "请帮我比对监控复电日志和北塔标准钟。",
        "testimony": "没看清脸", "record": "快八分钟", "correct": ("罗钧", "掩盖虚报货重"),
    },
    {
        "case": "example_4", "helper": "太平公主", "witness": "御史大夫", "specialist": "御史大夫",
        "ask": "劳烦你向御史打听一下宫闱秘录的借阅登记。", "direct": "你知道秘录登记写了什么吗？",
        "origin": "谁来问过秘录登记？", "check": "请帮我查阅御史台副册，核对宫闱秘录出库签押。",
        "testimony": "签押", "record": "出库栏均无签押", "correct": ("武惠妃", "掩盖武氏家族贪墨军饷"),
    },
)


def execute(client, database, route, rows):
    token = client.start(route["case"])
    result = {"case": route["case"], "passed": False, "turns": []}
    rows.append(result)

    def say(request_id, actor, text):
        reply = client.say(token, request_id, actor, text)
        result["turns"].append({"actor": actor, "input": text, "outcome": reply})
        assert reply["driver"] == "llm", reply
        return reply

    def task(request_id, actor, text, fragment):
        receipt = say(request_id, actor, text)
        assert (receipt.get("task") or {}).get("status") == "accepted", receipt
        reply = client.resume(token, receipt["task"]["id"])
        assert reply["driver"] == "llm" and reply["task"]["status"] == "completed", reply
        assert fragment in reply["reply"], reply
        assert client.resume(token, reply["task"]["id"]) == reply
        result["turns"][-1]["settled"] = reply
        return reply

    try:
        say("chat", route["helper"], "你好，今天天气不错。")
        assert route["testimony"] in task("contact", route["helper"], route["ask"], route["testimony"])["reply"]
        say("direct", route["witness"], route["direct"])
        say("receipt", route["witness"], "有人来问过西门出入吗？" if route["case"] == "harbor_blackout"
            else "有人查过秘录登记吗？")
        assert route["helper"] in say("origin", route["witness"], route["origin"])["reply"]
        checked = task("object", route["specialist"], route["check"], route["record"])
        assert checked["turn"]["classification"] == "fact"
        assert "哪" in say("clarify", route["helper"], "有件事想请你代劳，具体对象我还没想好。")["reply"]
        previous_tasks = client.call("state", token=token)["tasks"]
        plan = client.call("assist", {"level": "plan", "query": "找出相互独立的证词与可核查的记录"}, token)
        assert plan["driver"] == "llm" and plan["steps"]
        assert client.call("state", token=token)["tasks"] == previous_tasks
        result["preview_steps"] = plan["steps"]
        client.call("assist", {"level": "answer"}, token, status=400)
        suspect, motive = route["correct"]
        assert client.call("verdict", {"suspect": suspect, "motive": motive}, token)["correct"]
        assert client.call("assist", {"level": "answer"}, token)["text"]
        result["passed"] = True
    finally:
        document = snapshot(database, token)
        result["model"] = document["model"]
        result["events"] = document["events"]
        result["passed"] = result["passed"] and all(
            entry["driver"] == "llm" and entry["status"] == "ok" for entry in result["model"]["audit"])
    assert result["passed"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    port = free_port()
    report = {"mode": "llm-required", "scenarios": []}
    failed = False
    try:
        with TemporaryDirectory(prefix="g03-strict-") as path:
            folder = Path(path)
            with serve_api(folder, port, None, live=True, llm_required=True) as pid:
                report["pid"] = pid
                for route in ROUTES:
                    try:
                        execute(Client(port), folder / "npc.db", route, report["scenarios"])
                    except (AssertionError, KeyError, TypeError) as error:
                        failed = True
                        report["scenarios"][-1]["error"] = str(error)
                print(f"FastAPI {pid}: " + ", ".join(f"{row['case']}={row['passed']}" for row in report["scenarios"]))
    finally:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
