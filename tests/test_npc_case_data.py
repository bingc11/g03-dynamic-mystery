import json
import sys
import unittest
from pathlib import Path


API = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(API))
from npc_case_data import validate_case


def packaged_case(case_id):
    return json.loads((API / "npc_cases" / f"{case_id}.json").read_text(encoding="utf-8"))


class CaseDataTests(unittest.TestCase):
    def test_authority_and_display_options_validate_for_both_packaged_cases(self):
        for path in sorted((API / "npc_cases").glob("*.json")):
            with self.subTest(case=path.stem):
                case = packaged_case(path.stem)
                self.assertIs(validate_case(case, expected_id=path.stem), case)
                self.assertIn(case["truth"]["suspect"], case["verdict"]["suspects"])
                self.assertIn(case["truth"]["motive"], case["verdict"]["motives"])

    def test_case_id_and_correct_verdict_must_match_the_public_options(self):
        case = packaged_case("example_4")
        with self.assertRaisesRegex(ValueError, r"case\.id"):
            validate_case(case, expected_id="different_case")
        case["verdict"]["motives"].remove(case["truth"]["motive"])
        with self.assertRaisesRegex(ValueError, r"truth\.motive"):
            validate_case(case)

    def test_unauthorized_reaction_and_unbound_records_are_rejected(self):
        case = packaged_case("harbor_blackout")
        case["reactions"]["gate"]["罗钧"] = ["ask_guard"]
        with self.assertRaisesRegex(ValueError, "reaction is not authorized"):
            validate_case(case)
        del case["reactions"]["gate"]["罗钧"]
        case["actions"]["ask_guard"]["record"] = "missing_record"
        with self.assertRaisesRegex(ValueError, r"actions\.ask_guard\.record"):
            validate_case(case)

    def test_hidden_evidence_requires_a_reachable_successful_grant(self):
        for obstruction in ("circular", "unavailable"):
            with self.subTest(obstruction=obstruction):
                case = packaged_case("harbor_blackout")
                if obstruction == "circular":
                    case["actions"]["inspect_audit_receipt"]["requires"].append("harbor_audit_receipt")
                else:
                    case["records"]["audit_receipt"]["available"] = False
                with self.assertRaisesRegex(ValueError, "no reachable grant for harbor_audit_receipt"):
                    validate_case(case)


if __name__ == "__main__":
    unittest.main()
