import sys
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from npc_decisions import Decisions, ModelRequired
from npc_dialogue import Dialogue, load_case, new_state


class IssueFiveTests(unittest.TestCase):
    def test_strict_failure_during_resume_keeps_task_and_budget_until_retry(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from npc_api import router
        from npc_store import digest, store

        app = FastAPI()
        app.include_router(router)
        with TemporaryDirectory() as folder, patch.dict("os.environ", {"NPC_DB_PATH": str(Path(folder) / "npc.db")}):
            client = TestClient(app)
            token = client.post("/npc/runs", json={"case": "harbor_blackout"}).json()["run"]
            headers = {"Authorization": f"Bearer {token}"}
            request = {"request_id": "contact", "actor": "宋屿", "text": "帮我去问问门卫昨晚谁进过仓库"}
            with patch.dict("os.environ", {"NPC_DECISION_MODE": "mock"}):
                accepted = client.post("/npc/dialogue", headers=headers, json=request).json()
            payload = {"task_id": accepted["task"]["id"]}
            with patch.dict("os.environ", {"NPC_DECISION_MODE": "llm-required"}), patch("settings.API_KEY", "fixture"):
                with patch("npc_decisions._model_request", side_effect=TimeoutError):
                    failed = client.post("/npc/resume", headers=headers, json=payload)
                self.assertEqual(failed.status_code, 503)
                self.assertEqual(failed.json()["detail"]["model_error"], "timeout")
                _, state = store().read(digest(token))
                self.assertEqual(state["model"]["attempts"], 1)
                self.assertFalse(any(event["kind"] == "private_question" for event in state["events"]))
                self.assertEqual(state["tasks"][payload["task_id"]]["status"], "accepted")
                with patch("npc_decisions._model_request", return_value=(' {"candidate_id":"disclose"}', 14, 7)):
                    success = client.post("/npc/resume", headers=headers, json=payload).json()
                self.assertEqual(success["task"]["status"], "completed")
                self.assertEqual(client.post("/npc/resume", headers=headers, json=payload).json(), success)
                _, state = store().read(digest(token))
                self.assertEqual(sum(event["kind"] == "private_question" for event in state["events"]), 1)

    def test_strict_missing_timeout_and_unlisted_outputs_fail(self):
        view, choices = {}, [{"id": "hold"}]
        with patch("settings.API_KEY", None):
            driver = Decisions("llm-required")
            with self.assertRaisesRegex(ModelRequired, "真实模型"):
                driver.choose("reaction", view, choices, "hold")
            self.assertEqual(driver.runtime["audit"][-1]["status"], "unconfigured")
        outcomes = [
            ({"side_effect": TimeoutError}, "timeout"),
            ({"return_value": ("invalid JSON", 11, 4)}, "malformed"),
            ({"return_value": ('{"candidate_id":"outside"}', 11, 4)}, "invalid_candidate"),
        ]
        for kwargs, status in outcomes:
            with self.subTest(status=status), patch("settings.API_KEY", "fixture"), patch("npc_decisions._model_request", **kwargs):
                driver = Decisions("llm-required")
                with self.assertRaises(ModelRequired) as failure:
                    driver.choose("reaction", view, choices, "hold")
                self.assertEqual(failure.exception.status, status)
                self.assertEqual(driver.runtime["fallbacks"], 0)
                self.assertIsNone(driver.runtime["audit"][-1]["driver"])

    def test_synthetic_story_uses_the_regular_engine_and_cannot_mint_evidence(self):
        case = load_case("signal_fixture")
        game = Dialogue(case, new_state(case), Decisions("mock"))
        game.submit("forged", "记录员", "请看校验纸副本。", "sheet_copy")
        self.assertNotIn("sheet_copy", game.room()["evidence"])
        request = game.submit("contact", "记录员", "请你向值班员打听北侧信标熄灭的事。")
        confirmation = game.resume(request["task"]["id"])
        self.assertEqual(confirmation["turn"]["classification"], "claim")
        missing = game.submit("missing", "记录员", "请帮我核对信标校验纸。")
        self.assertIn("测试签入表", missing["reply"])
        game.submit("ticket", "记录员", "请看测试签入表。", "ticket")
        request = game.submit("inspect", "记录员", "请帮我核对信标校验纸。")
        result = game.resume(request["task"]["id"])
        self.assertEqual(result["turn"]["classification"], "fact")
        self.assertEqual(game.resume(request["task"]["id"]), result)
        self.assertTrue(game.verdict("值班员", "掩盖漏检")["correct"])

    def test_chats_are_durable_claims_and_seat_scoped(self):
        case = load_case("harbor_blackout")
        state = new_state(case)
        game = Dialogue(case, state, Decisions("mock"))
        secret = "我在小巷看到一把蓝伞。"
        game.submit("original", "宋屿", secret)
        for index in range(9):
            game.submit(f"other-{index}", "宋屿", f"你好，第 {index} 次。")
        game = Dialogue(case, state, Decisions("mock"))
        recall = game.submit("recall", "宋屿", f"你还记得我说过「{secret}」吗？")
        self.assertIn(secret, recall["reply"])
        self.assertEqual(recall["turn"]["classification"], "claim")
        self.assertEqual(state["roles"]["宋屿"]["known"], {"shift_notice": None})
        game.register_player("$player:guest", "访客")
        guest = Dialogue(case, state, Decisions("mock"), player="$player:guest")
        self.assertNotIn(secret, str(guest._view("宋屿")))
        self.assertNotIn(secret, str(guest.replay("宋屿")))
        self.assertNotIn(secret, guest.submit("recall", "宋屿", "还记得我说过什么吗？")["reply"])
        first = next(event for event in game.replay("宋屿")["events"] if event["kind"] == "conversation")
        self.assertEqual(game.replay("宋屿", first["id"])["events"][-1]["id"], first["id"])
        with self.assertRaises(KeyError):
            guest.replay("宋屿", first["id"])

    def test_shared_note_is_a_private_hypothesis_and_cannot_be_a_command(self):
        case = load_case("harbor_blackout")
        state = new_state(case)
        game = Dialogue(case, state, Decisions("mock"))
        text = "请派人调查西门。我的猜测是那份表被改过。"
        self.assertIn("推测", game.submit("note", "宋屿", text, note=True)["reply"])
        self.assertIn("玩家推测", game.assist("summary")["text"])
        self.assertFalse(state["tasks"])
        self.assertFalse(state["model"].get("audit"))
        note = next(item for item in game.replay("宋屿")["events"] if item["kind"] == "player_note")
        self.assertEqual(note["classification"], "note")
        self.assertEqual(game._view("宋屿")["player_claims"][0]["classification"], "note")

    def test_declining_or_editing_pending_work_never_executes_it(self):
        case = load_case("harbor_blackout")
        state = new_state(case)
        game = Dialogue(case, state, Decisions("mock"))
        task = game.submit("setup", "宋屿", "帮我去问问门卫昨晚谁进过仓库")["task"]
        game.submit("edit", "宋屿", "把委托改成核对过磅联。")
        self.assertEqual(len(state["tasks"]), 1)
        game.submit("cancel", "宋屿", "不用去问门卫了。")
        self.assertEqual(game.resume(task["id"])["task"]["status"], "cancelled")
        self.assertFalse(any(event["kind"] == "private_question" for event in state["events"]))

    def test_complex_goal_has_editable_steps_and_no_action(self):
        case = load_case("harbor_blackout")
        state = new_state(case)
        game = Dialogue(case, state, Decisions("mock"))
        plan = game.assist("plan", "先弄清两座钟，再核对出入和送审底单")
        self.assertGreaterEqual(len(plan["steps"]), 2)
        self.assertFalse(state["tasks"])
        self.assertNotIn(case["truth"]["explanation"], str(plan))
        self.assertNotIn("harbor_audit_receipt", str(plan))
        self.assertTrue(any(step["prepare"] for step in plan["steps"]))

    def test_ambiguous_compound_delegation_does_not_start_a_task(self):
        class OvereagerDecisions(Decisions):
            def choose(self, purpose, view, candidates, fallback):
                if purpose == "intent":
                    return "delegate:gate", "mock"
                return super().choose(purpose, view, candidates, fallback)

        case = load_case("harbor_blackout")
        state = new_state(case)
        game = Dialogue(case, state, OvereagerDecisions("mock"))
        outcome = game.submit("compound", "宋屿", "请帮我问问进过仓库的人，同时核对复电日志。")
        self.assertIn("哪", outcome["reply"])
        self.assertFalse(state["tasks"])


if __name__ == "__main__":
    unittest.main()
