import sys
import unittest
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from npc_actions import CENSOR, MANUSCRIPT, PLAYER, PRINCESS, WITNESS, Choice, Investigation


class ActionTests(unittest.TestCase):
    def test_show_changes_one_other_characters_next_investigation(self):
        game = Investigation()
        self.assertIn("没有收到", game.apply(0, "ask", CENSOR, "registry")["reply"])
        game.apply(1, "show", PRINCESS, MANUSCRIPT)
        self.assertIn("可以再问", game.apply(2, "ask", CENSOR, "registry")["reply"])
        self.assertIn(PRINCESS, game.apply(3, "ask", CENSOR, "registry_origin")["reply"])
        self.assertEqual(game.memory[WITNESS], [])
        self.assertEqual(game.memory[CENSOR][0].kind, "heard_claim")
        self.assertNotEqual(game.memory[CENSOR][0].source, MANUSCRIPT)

    def test_show_someone_else_and_no_show_are_controls(self):
        for recipient in (None, CENSOR, WITNESS):
            game = Investigation()
            if recipient:
                game.apply(0, "show", recipient, MANUSCRIPT)
            self.assertIn("没有收到", game.apply(game.version, "ask", CENSOR, "registry")["reply"])
            self.assertFalse(any(e.kind == "private_question" for e in game.events))

    def test_private_contact_is_not_returned_as_a_player_observation(self):
        game = Investigation()
        result = game.apply(0, "show", PRINCESS, MANUSCRIPT)
        private = next(e for e in game.events if e.kind == "private_question")
        self.assertNotIn(PLAYER, private.audience)
        self.assertNotIn(CENSOR, str(result))
        self.assertEqual(set(result), {"version", "reply", "driver"})
        self.assertEqual(game.events[private.cause-1].kind, "accepted")

    def test_controller_receives_only_own_view_and_cannot_invent_or_retarget(self):
        for bad in (Choice("rewrite_truth", CENSOR, MANUSCRIPT), Choice("ask_registry", WITNESS, MANUSCRIPT),
                    Choice("ask_registry", CENSOR, "secret_other"), None):
            def fake(view):
                self.assertEqual(view.actor, PRINCESS)
                self.assertEqual([m.source for m in view.memory], [MANUSCRIPT])
                return bad
            game = Investigation()
            game.apply(0, "show", PRINCESS, MANUSCRIPT, fake)
            self.assertEqual(game.events[-1].kind, "rejected")
            self.assertEqual(game.memory[CENSOR], [])

    def test_policy_failure_stops_without_propagation(self):
        game = Investigation()
        def unavailable(_):
            raise TimeoutError()
        game.apply(0, "show", PRINCESS, MANUSCRIPT, unavailable)
        self.assertEqual([e.kind for e in game.events], ["show", "rejected"])
        self.assertIn("没有收到", game.apply(1, "ask", CENSOR, "registry")["reply"])

    def test_same_receipt_stale_version_and_unknown_player_commands(self):
        game = Investigation()
        game.apply(0, "show", PRINCESS, MANUSCRIPT)
        before = list(game.events)
        for command in [(0, "ask", CENSOR, "registry"), (1, "show", PRINCESS, MANUSCRIPT),
                        (1, "show", CENSOR, "made-up"), (1, "accuse", PLAYER, "registry"),
                        (1, "ask", CENSOR, "registry_origin")]:
            with self.assertRaises(ValueError):
                game.apply(*command)
            self.assertEqual(game.events, before)
            self.assertEqual(game.version, 1)

    def test_trace_and_scope_are_repeatable(self):
        def replay():
            game = Investigation()
            game.apply(0, "show", PRINCESS, MANUSCRIPT)
            game.apply(1, "ask", CENSOR, "registry")
            return [asdict(e) for e in game.events]
        self.assertEqual(replay(), replay())
        self.assertFalse(Investigation().memory[CENSOR])

if __name__ == "__main__":
    unittest.main()
