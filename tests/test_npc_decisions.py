import json
from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

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
        request.return_value = ('{"candidate_id":"unknown-action"}', 37, 8)
        decisions = Decisions("llm")
        visible = {"knowledge": [{"source": "record-1"}]}
        legal = [{"id": "wait", "label": "稍候"}]
        for _ in range(MAX_MODEL_CALLS):
            self.assertEqual(decisions.choose("plan", visible, legal, "wait"), ("unknown-action", "llm"))
        self.assertEqual(decisions.choose("plan", visible, legal, "wait"), ("wait", "rules"))
        self.assertEqual(request.call_count, MAX_MODEL_CALLS)
        self.assertEqual(json.loads(request.call_args.args[1]), {"view": visible, "candidates": legal})
        self.assertEqual(decisions.runtime["outcomes"], {"invalid_candidate": MAX_MODEL_CALLS, "budget_exhausted": 1})
        self.assertNotIn("unknown-action", json.dumps(decisions.runtime))

    @patch("npc_decisions._configured", return_value=True)
    @patch("npc_decisions._model_request")
    def test_model_schema_and_outages_fall_back_to_rules(self, request, _):
        request.side_effect = [
            ('{"candidate_id":"wait","reply":"未验证的结果"}', 20, 10),
            ('{"candidate_id":3}', 20, 5),
            ConnectionError,
        ]
        decisions = Decisions("llm")
        for _ in range(3):
            self.assertEqual(decisions.choose("plan", {}, [{"id": "wait"}], "wait"), ("wait", "rules"))
        self.assertEqual(decisions.runtime["retries"], 1)
        self.assertEqual(decisions.runtime["fallbacks"], 3)
        self.assertEqual(decisions.runtime["outcomes"], {"malformed": 2, "connection_error": 1, "budget_exhausted": 1})
        self.assertGreater(decisions.runtime["input_budget_used"], decisions.runtime["input_tokens"])

    @patch("npc_decisions._configured", return_value=True)
    @patch("npc_decisions.MODEL_TIMEOUT", 0.01)
    @patch("npc_decisions._model_request")
    def test_model_deadline_returns_even_when_provider_is_unresponsive(self, request, _):
        release_provider = Event()
        request.side_effect = lambda *args: release_provider.wait(timeout=1)
        try:
            decisions = Decisions("llm")
            self.assertEqual(decisions.choose("plan", {}, [{"id": "wait"}], "wait"), ("wait", "rules"))
            self.assertEqual(decisions.runtime["outcomes"], {"timeout": 1})
            self.assertEqual(decisions.runtime["retries"], 0)
        finally:
            release_provider.set()

    @patch("npc_decisions._configured", return_value=True)
    @patch("npc_decisions._model_request")
    def test_json_retry_reports_usage_and_keeps_only_a_safe_request_digest(self, request, _):
        request.side_effect = [
            ("    ", 23, 5),
            ('{"candidate_id":"inspect"}', 22, 8),
        ]
        state = {}
        decisions = Decisions("llm", runtime=state)
        candidates = [{"id": "wait"}, {"id": "inspect"}]
        self.assertEqual(decisions.choose("plan", {"secret": "private sample"}, candidates, "wait"), ("inspect", "llm"))
        self.assertEqual((state["attempts"], state["retries"], state["fallbacks"]), (2, 1, 0))
        self.assertEqual((state["input_tokens"], state["output_tokens"]), (45, 13))
        rejected, selected = state["audit"]
        self.assertEqual((rejected["status"], selected["status"]), ("malformed", "ok"))
        self.assertEqual(rejected["request_sha256"], selected["request_sha256"])
        self.assertEqual(len(selected["request_sha256"]), 64)
        self.assertNotIn("private sample", json.dumps(state))

    @patch("npc_decisions._configured", return_value=True)
    @patch("npc_decisions.MAX_MODEL_RUN_CALLS", 2)
    @patch("npc_decisions._model_request", return_value=('{"candidate_id":"wait"}', 19, 7))
    def test_playthrough_budget_survives_separate_interactions(self, request, _):
        runtime = {}
        candidates = [{"id": "wait"}]
        for _ in range(2):
            self.assertEqual(
                Decisions("llm", runtime=runtime).choose("plan", {}, candidates, "wait"), ("wait", "llm")
            )
            runtime = json.loads(json.dumps(runtime))
        self.assertEqual(Decisions("llm", runtime=runtime).choose("plan", {}, candidates, "wait"), ("wait", "rules"))
        self.assertEqual(request.call_count, 2)
        self.assertEqual(runtime["outcomes"], {"ok": 2, "budget_exhausted": 1})

    @patch("npc_decisions._configured", return_value=True)
    @patch("npc_decisions.MAX_MODEL_RUN_OUTPUT_TOKENS", 1)
    @patch("npc_decisions._model_request")
    def test_token_budget_rejects_a_call_before_the_provider(self, request, _):
        decisions = Decisions("llm")
        self.assertEqual(decisions.choose("plan", {}, [{"id": "wait"}], "wait"), ("wait", "rules"))
        request.assert_not_called()


class DeepSeekAdapterTests(unittest.TestCase):
    @patch("llm_service.INFERENCE_SERVICE", "deepseek")
    @patch("llm_service.DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    @patch("llm_service.MODEL", "deepseek-flash")
    @patch("llm_service.API_KEY", "fixture-only")
    @patch("llm_service.openai.OpenAI")
    def test_structured_and_streaming_runtime_use_official_deepseek_settings(self, factory):
        from invoke_types import LLMMessage
        from llm_service import invoke_openai, invoke_openai_stream

        create = factory.return_value.__enter__.return_value.chat.completions.create
        create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content='{"candidate_id":"wait"}', reasoning_content="private", refusal=None),
            )],
            usage=SimpleNamespace(prompt_tokens=20, completion_tokens=6),
        )
        messages = [LLMMessage(role="user", content="fixture")]
        self.assertEqual(
            invoke_openai("Return JSON", messages, timeout=4, max_tokens=96, json_output=True),
            ('{"candidate_id":"wait"}', 20, 6),
        )
        self.assertEqual(factory.call_args.kwargs["base_url"], "https://api.deepseek.com")
        self.assertEqual(factory.call_args.kwargs["timeout"], 4)
        self.assertEqual(factory.call_args.kwargs["max_retries"], 0)
        self.assertEqual(create.call_args.kwargs["model"], "deepseek-flash")
        self.assertEqual(create.call_args.kwargs["response_format"], {"type": "json_object"})
        self.assertEqual(create.call_args.kwargs["extra_body"], {"thinking": {"type": "disabled"}})

        stream = MagicMock()
        stream.__iter__.return_value = iter([
            SimpleNamespace(choices=[SimpleNamespace(
                finish_reason=None, delta=SimpleNamespace(content=None, reasoning_content="private"),
            )]),
            SimpleNamespace(choices=[SimpleNamespace(
                finish_reason="stop", delta=SimpleNamespace(content="可见答复"),
            )]),
            SimpleNamespace(choices=[]),
        ])
        create.return_value = stream
        self.assertEqual(list(invoke_openai_stream("Respond to player", messages)), ["可见答复"])
        self.assertTrue(create.call_args.kwargs["stream"])
        self.assertNotIn("response_format", create.call_args.kwargs)
        self.assertEqual(create.call_args.kwargs["extra_body"], {"thinking": {"type": "disabled"}})

    @patch("llm_service.INFERENCE_SERVICE", "deepseek")
    @patch("llm_service.API_KEY", "fixture-only")
    @patch("llm_service.openai.OpenAI")
    def test_provider_exception_exposes_status_without_raw_body(self, factory):
        import openai
        from llm_service import ProviderFailure, invoke_openai

        class AuthenticationFailure(openai.APIError):
            status_code = 401

            def __init__(self):
                Exception.__init__(self, "provider echoed credential fixture-only")

        create = factory.return_value.__enter__.return_value.chat.completions.create
        create.side_effect = AuthenticationFailure
        with self.assertRaises(ProviderFailure) as caught:
            invoke_openai("Return JSON", [], timeout=4, max_tokens=96, json_output=True)
        self.assertEqual(caught.exception.status_code, 401)
        self.assertNotIn("fixture-only", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
