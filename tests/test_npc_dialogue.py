import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from npc_decisions import Decisions
from npc_dialogue import Dialogue, PLAYER, load_case, new_state


class RecordingDecisions(Decisions):
    def __init__(self):
        super().__init__("mock")
        self.views = []

    def choose(self, purpose, view, candidates, fallback):
        self.views.append((purpose, view, {item["id"] for item in candidates}))
        return super().choose(purpose, view, candidates, fallback)


class DialogueTests(unittest.TestCase):
    def test_same_evidence_three_roles_choose_using_their_goals_and_permissions(self):
        case = load_case("example_4")
        evidence = "evidence_manuscript_missing"
        for actor, action, event_kind, knowledge in (
            ("太平公主", "consult_registry", "private_question", "archive_location"),
            ("御史大夫", "inspect_registry", "object_read", "registry_copy"),
            ("张昌宗", "hold", None, "sachet_mark"),
        ):
            with self.subTest(actor=actor):
                state = new_state(case)
                decisions = RecordingDecisions()
                dialogue = Dialogue(case, state, decisions)
                dialogue.submit("show", actor, "请看遗失的宫闱秘录。", evidence)
                shown, reaction, *effects = state["events"]
                self.assertEqual((shown["kind"], shown["source"], shown["result"]["text"]),
                                 ("show", evidence, case["evidence"][evidence]["text"]))
                self.assertEqual((reaction["kind"], reaction["driver"], reaction["result"]["proposal"]),
                                 ("decision", "mock", action))
                self.assertEqual(reaction["cause"], shown["id"])
                if event_kind:
                    self.assertEqual(effects[0]["kind"], event_kind)
                    self.assertEqual(effects[0]["cause"], reaction["id"])
                else:
                    self.assertEqual(effects, [])
                purpose, view, choices = decisions.views[0]
                self.assertEqual(purpose, "reaction")
                self.assertEqual(view["goal"], case["roles"][actor]["goal"])
                self.assertEqual(view["relations"], case["roles"][actor]["relations"])
                self.assertIn(knowledge, [record["id"] for record in view["knowledge"]])
                self.assertEqual(view["events"], [shown])
                self.assertIn(action, choices)

    def test_receiver_state_changes_the_lead_given_by_the_same_private_message(self):
        case = load_case("harbor_blackout")
        actor = "宋屿"
        sender = "林遥"
        contacts = []
        for trust, stance, followup in ((1, "accept", "去问阮岑"), (0, "question", "请林遥核对")):
            with self.subTest(trust=trust):
                state = new_state(case)
                state["roles"][actor]["relations"][sender] = trust
                decisions = RecordingDecisions()
                dialogue = Dialogue(case, state, decisions)
                dialogue.submit("show", sender, "请看监控校时便条。", "harbor_clock_strip")
                result = dialogue.submit("followup", actor, "监控校时有消息吗？")
                self.assertIn(followup, result["reply"])
                contact = next(event for event in state["events"] if event["kind"] == "private_message")
                self.assertCountEqual(contact["audience"], [sender, actor])
                contacts.append(contact["result"])
                self.assertEqual(state["roles"][actor]["beliefs"][contact["id"]]["state"], stance)
                self.assertNotIn("clock_claim", state["roles"][actor]["known"])
                self.assertFalse(any(event["kind"] == "object_read" for event in state["events"]))
                receiver_view = next(view for purpose, view, _ in decisions.views if purpose == "response")
                self.assertEqual([event["id"] for event in receiver_view["events"]], [contact["id"]])
                self.assertEqual([item["id"] for item in receiver_view["knowledge"]], ["shift_notice"])
                self.assertNotIn(contact["id"], str(dialogue.public_state()))
                self.assertNotIn(PLAYER, contact["audience"])
        self.assertEqual(contacts[0], contacts[1])

    def test_illegal_candidate_cannot_change_state_and_is_audited(self):
        class InvalidDecision(Decisions):
            def choose(self, purpose, view, candidates, fallback):
                if purpose == "plan":
                    return "inspect_sealed", "mock"
                return super().choose(purpose, view, candidates, fallback)

        case = load_case("example_4")
        state = new_state(case)
        game = Dialogue(case, state, InvalidDecision("mock"))
        result = game.submit("delegate", "太平公主", "请帮我核对秘录的借阅登记。")
        self.assertIn("没能确认一条可执行", result["reply"])
        self.assertFalse(state["tasks"])
        self.assertNotIn("sealed_roll", state["roles"]["太平公主"]["known"])
        rejected = next(event for event in state["events"] if event["kind"] == "rejected")
        self.assertEqual(rejected["result"]["status"], "illegal_candidate")
        self.assertEqual(rejected["driver"], "mock")
        self.assertEqual(rejected["audience"], [])
        self.assertFalse(any(event["kind"] in ("private_question", "object_read") for event in state["events"]))


if __name__ == "__main__":
    unittest.main()
