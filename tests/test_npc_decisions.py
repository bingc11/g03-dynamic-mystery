import json
from pathlib import Path
import sys
from threading import Event
import unittest
from unittest.mock import patch

API = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(API))

from npc_decisions import Decisions, MAX_MODEL_CALLS, classify


def view(case, text, pending=None, observed=()):
    topics = json.loads((API / "npc_cases" / f"{case}.json").read_text(encoding="utf-8"))["topics"]
    return {
        "text": text,
        "topics": [{"id": topic_id, "label": topic["label"], "aliases": topic["aliases"]}
                   for topic_id, topic in topics.items()],
        "pending_topic": pending,
        "observed_topics": observed,
    }


class DecisionTests(unittest.TestCase):
    def test_mock_interprets_delegation_across_cases_and_paraphrases(self):
        for case, text, expected in [
            ("example_4", "劳烦你向御史打听一下宫闱秘录的借阅登记。", "delegate:registry"),
            ("example_4", "请帮我对一对宫闱秘录的借阅登记。", "delegate:registry"),
            ("example_4", "烦请查一查封存的内廷名册。", "delegate:sealed"),
            ("example_4", "麻烦翻一翻雨夜那份原簿。", "delegate:archive"),
            ("harbor_blackout", "帮我去问问门卫昨晚谁进过仓库", "delegate:gate"),
            ("harbor_blackout", "劳烦去找值门人打听昨天夜里哪些人进过库房。", "delegate:gate"),
            ("harbor_blackout", "替我核对这两份证词。", "delegate:timing"),
            ("harbor_blackout", "这两份口供能请你帮忙对一下吗？", "delegate:timing"),
            ("harbor_blackout", "劳你查一下七号背心的领用表。", "delegate:supply"),
            ("harbor_blackout", "有劳翻翻背心领用记录。", "delegate:supply"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(Decisions("mock").choose(
                    "intent", view(case, text), [{"id": expected}], "chat"
                ), (expected, "mock"))

    def test_mock_distinguishes_inquiries_chitchat_and_clarification(self):
        for case, text, pending, observed, expected in [
            ("example_4", "你今天心情怎么样？", None, (), "chat"),
            ("example_4", "不用帮我查宫闱秘录的借阅登记。", None, (), "chat"),
            ("example_4", "能不能替我查一件事？", None, (), "clarify"),
            ("example_4", "就是那份归档原簿。", "archive", (), "delegate:archive"),
            ("example_4", "雨夜原簿", "", (), "delegate:archive"),
            ("example_4", "我说的是雨夜里那本归档原簿。", "", (), "delegate:archive"),
            ("example_4", "请你查之前谁来过", None, (), "clarify"),
            ("example_4", "有人查过秘录登记吗？", None, (), "receipt:registry"),
            ("example_4", "谁来问过秘录登记？", None, (), "origin:registry"),
            ("example_4", "谁来问过你这件事？", None, ("registry",), "origin:registry"),
            ("harbor_blackout", "有谁来打听过昨晚西门的出入吗？", None, (), "origin:gate"),
            ("harbor_blackout", "能否告诉我你核对过七号背心的领用表没有？", None, (), "followup:supply"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(classify(view(case, text, pending, observed)), expected)

    def test_witness_inquiries_and_investigation_updates_use_distinct_intents(self):
        for case, text, observed, expected in [
            ("harbor_blackout", "昨晚西门谁进过仓库？", (), "inquire:gate"),
            ("harbor_blackout", "昨晚哪些人从西门进出，你有看到吗？", ("gate",), "inquire:gate"),
            ("example_4", "秘录登记写了什么？", (), "inquire:registry"),
            ("harbor_blackout", "有人提过监控时间的误差吗？", (), "receipt:timing"),
            ("harbor_blackout", "收到关于西门出入的新消息了吗？", (), "receipt:gate"),
            ("harbor_blackout", "之前有人来问过吗？", ("gate",), "receipt:gate"),
            ("harbor_blackout", "西门的出入有消息吗？", (), "followup:gate"),
            ("harbor_blackout", "有什么结果了吗？", ("gate",), "followup:gate"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(classify(view(case, text, observed=observed)), expected)

        topics = [{"id": "gate", "label": "West gate entries", "aliases": ["west gate"]}]
        self.assertEqual(classify({"text": "Who entered through the west gate?", "topics": topics}), "inquire:gate")
        self.assertEqual(classify({"text": "Any updates on the west gate?", "topics": topics}), "followup:gate")
        self.assertEqual(classify({"text": "Did anyone ask about the west gate?", "topics": topics}), "receipt:gate")
        self.assertEqual(classify({"text": "Did anyone tell you about the west gate?", "topics": topics}), "receipt:gate")
        self.assertEqual(classify({"text": "Who contacted you about the west gate?", "topics": topics}), "origin:gate")

    def test_result_questions_do_not_start_another_investigation(self):
        for text, expected in [
            ("核对秘录登记的结果是什么？", "followup:registry"),
            ("核实秘录登记有什么结果吗？", "followup:registry"),
            ("你核查秘录登记查出什么了吗？", "followup:registry"),
            ("核实秘录登记的结果是什么", "followup:registry"),
            ("请核对秘录登记，查到结果再告诉我。", "delegate:registry"),
            ("查一下秘录登记。", "delegate:registry"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(classify(view("example_4", text)), expected)

    @patch("npc_decisions._configured", return_value=True)
    @patch("npc_decisions._model_request")
    def test_model_returns_an_id_for_validation_and_obeys_call_budget(self, request, _):
        request.return_value = '{"candidate_id":"unknown-action"}'
        decisions = Decisions("llm")
        visible = {"knowledge": [{"source": "record-1"}]}
        legal = [{"id": "wait", "label": "稍候"}]
        for _ in range(MAX_MODEL_CALLS):
            self.assertEqual(decisions.choose("plan", visible, legal, "wait"), ("unknown-action", "llm"))
        self.assertEqual(decisions.choose("plan", visible, legal, "wait"), ("wait", "rules"))
        self.assertEqual(request.call_count, MAX_MODEL_CALLS)
        self.assertEqual(json.loads(request.call_args.args[1]), {"view": visible, "candidates": legal})

    @patch("npc_decisions._configured", return_value=True)
    @patch("npc_decisions._model_request")
    def test_model_schema_and_outages_fall_back_to_rules(self, request, _):
        request.side_effect = [
            '{"candidate_id":"wait","reply":"未验证的结果"}',
            '{"candidate_id":3}',
            ConnectionError,
        ]
        decisions = Decisions("llm")
        for _ in range(3):
            self.assertEqual(decisions.choose("plan", {}, [{"id": "wait"}], "wait"), ("wait", "rules"))

    @patch("npc_decisions._configured", return_value=True)
    @patch("npc_decisions.MODEL_TIMEOUT", 0.01)
    @patch("npc_decisions._model_request")
    def test_model_deadline_returns_even_when_provider_is_unresponsive(self, request, _):
        release_provider = Event()
        request.side_effect = lambda *args: release_provider.wait(timeout=1)
        try:
            self.assertEqual(Decisions("llm").choose("plan", {}, [{"id": "wait"}], "wait"), ("wait", "rules"))
        finally:
            release_provider.set()


if __name__ == "__main__":
    unittest.main()
