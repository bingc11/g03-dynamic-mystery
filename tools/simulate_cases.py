"""Evaluate packaged NPC cases with the same fixed prompts and gameplay checks."""

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys
from time import monotonic


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
from npc_decisions import Decisions
from npc_dialogue import Dialogue, load_case, new_state


FIXTURES = Path(__file__).with_name("npc_scenarios.json")
GUEST = "$player:evaluation-guest"
CHOICE_PURPOSES = {"plan", "reaction", "response"}
LINKED_KINDS = {"accepted", "claim", "private_question", "private_message", "report", "reception", "object_read"}
MAX_EVENTS_PER_STEP = 24
MAX_ATTEMPTS_PER_INTERACTION = 3


class Probe:
    """Observe the exact role projection presented to the configured decision driver."""

    def __init__(self, mode, state, budget, checks):
        self.mode = mode
        self.state = state
        self.runtime = state.setdefault("model", {})
        self.driver = Decisions(mode, runtime=self.runtime)
        self.rules = Decisions("rules", runtime=self.runtime)
        self.budget = budget
        self.checks = checks

    def choose(self, purpose, view, candidates, fallback):
        actor = view.get("actor")
        role = self.state["roles"].get(actor)
        if role is not None:
            for item in view.get("knowledge", []):
                self.checks["role_knowledge_overreach"] += item["id"] not in role["known"]
            for event in view.get("events", []):
                audience = event.get("audience", [])
                self.checks["private_model_exposure"] += actor not in audience
        start = self.runtime.get("attempts", 0)
        delta = MAX_ATTEMPTS_PER_INTERACTION
        if self.mode == "llm" and self.budget["used"] + delta > self.budget["limit"]:
            self.checks["evaluation_budget_blocks"] += 1
            return self.rules.choose(purpose, view, candidates, fallback)
        result = self.driver.choose(purpose, view, candidates, fallback)
        self.budget["used"] += self.runtime.get("attempts", 0) - start
        return result


def fraction(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def cause_chain(event, by_id):
    seen = set()
    while event is not None and event["id"] not in seen:
        seen.add(event["id"])
        yield event
        event = by_id.get(event["cause"])


def inspect_events(events, case, checks):
    by_id = {}
    for event in events:
        kind = event["kind"]
        cause = event["cause"]
        result = event["result"]
        checks["event_links_checked"] += bool(cause) or kind in LINKED_KINDS
        checks["invalid_event_links"] += (bool(cause) or kind in LINKED_KINDS) and cause not in by_id
        checks["duplicate_event_ids"] += event["id"] in by_id
        if kind in ("decision", "rejected") and result.get("purpose") in CHOICE_PURPOSES:
            checks["action_proposals"] += 1
            checks["legal_action_proposals"] += kind == "decision"
        if kind in ("object_read", "claim", "report"):
            checks["sources_checked"] += 1
            checks["missing_sources"] += not event["source"]
        if kind == "object_read":
            canonical = case["records"].get(event["source"], {})
            checks["fact_claim_errors"] += result.get("classification") != canonical.get("kind")
        if kind in ("claim", "private_message", "statement"):
            classification = result.get("classification")
            checks["fact_claim_errors"] += classification == "fact" or (kind == "claim" and classification != "claim")
        if kind == "report" and result.get("classification") == "fact":
            source = by_id.get(cause)
            checks["fact_claim_errors"] += not source or source["kind"] != "object_read"
        by_id[event["id"]] = event
    for report in [event for event in events if event["kind"] == "report"]:
        chain = list(cause_chain(report, by_id))
        kinds = {node["kind"] for node in chain}
        if not {"private_question", "claim", "reception"}.issubset(kinds):
            continue
        receipt = next(node for node in chain if node["kind"] == "reception")
        followup = any(event["kind"] == "statement" and event["cause"] == receipt["id"] for event in events)
        if followup:
            checks["private_contact_chains_with_followup"] += 1
            real = {node["result"].get("purpose") for node in chain if node.get("driver") == "llm"}
            checks["real_private_contact_chains_with_followup"] += {"intent", "plan", "response"}.issubset(real)
    return by_id


def check_player_views(game, state, case, checks):
    guest = Dialogue(case, state, Decisions("mock"), player=GUEST)
    private_ids = {event["id"] for event in state["events"] if "$player" in event["audience"]}
    guest_ids = {event["id"] for event in guest.replay()["events"]}
    checks["private_player_exposure"] += len(private_ids & guest_ids)
    checks["private_player_exposure"] += len(guest.public_state()["turns"]) + len(guest.public_state()["tasks"])
    settled_turns = [task["turn_id"] for task in game.public_state()["tasks"] if task["status"] == "completed"]
    if settled_turns:
        shared = game.share(settled_turns[0])["shared"]
        feed = guest.room()["public"]
        checks["public_shares_checked"] += 1
        checks["public_share_errors"] += sum(event["id"] == shared["id"] for event in feed) != 1
    try:
        game.assist("answer")
    except ValueError:
        checks["premature_answers_blocked"] += 1
    else:
        checks["premature_answer_exposure"] += 1


def run_scenario(scenario, mode, budget):
    case = load_case(scenario["case"])
    original_truth = deepcopy(case["truth"])
    state = new_state(case)
    checks = Counter()
    replies = []
    differences = []
    durations = []
    for actor, contact, trust in scenario.get("relations", []):
        state["roles"][actor]["relations"][contact] = trust
    Dialogue(case, state, Decisions("mock")).register_player(GUEST, "评测第二席")

    for index, step in enumerate(scenario["steps"], start=1):
        game = Dialogue(case, state, Probe(mode, state, budget, checks))
        started = monotonic()
        before = len(state["events"])
        result = game.submit(f"step-{index}", step["actor"], step["text"], step.get("evidence"))
        if (result.get("task") or {}).get("status") == "accepted":
            task_id = result["task"]["id"]
            result = Dialogue(case, state, Probe(mode, state, budget, checks)).resume(task_id)
            events = len(state["events"])
            attempts = state["model"].get("attempts", 0)
            duplicate = Dialogue(case, state, Probe(mode, state, budget, checks)).resume(task_id)
            checks["repeat_settlements_checked"] += 1
            checks["duplicate_settlements"] += (duplicate != result or len(state["events"]) != events
                                               or state["model"].get("attempts", 0) != attempts)
        durations.append(round((monotonic() - started) * 1000))
        checks["event_limit_exceeded"] += len(state["events"]) - before > MAX_EVENTS_PER_STEP
        reply = result.get("reply", "")
        task_status = (result.get("task") or {}).get("status")
        replies.append({"actor": step["actor"], "input": step["text"], "driver": result.get("driver"),
                        "task_status": task_status, "reply": reply[:300]})
        if step.get("task") and step["task"] != task_status:
            differences.append({"step": index, "expected_task": step["task"], "actual_task": task_status})
        if step.get("reply") and step["reply"] not in reply:
            differences.append({"step": index, "expected_reply_fragment": step["reply"], "actual_reply": reply[:300]})

    game = Dialogue(case, state, Decisions("mock"))
    before_audit = state["model"].get("attempts", 0)
    check_player_views(game, state, case, checks)
    checks["replay_or_assist_model_attempts"] += state["model"].get("attempts", 0) - before_audit
    wrong = game.verdict(*scenario["wrong"])
    correct = game.verdict(*scenario["correct"])
    checks["verdicts_checked"] = 2
    checks["verdict_errors"] += bool(wrong["correct"]) + (not correct["correct"])
    checks["solved"] = int(correct["correct"])
    if correct["correct"]:
        checks["debrief_errors"] += original_truth["explanation"] not in game.assist("answer")["text"]
    required = set(scenario.get("clues", []))
    observed = {event["source"] for event in game.replay()["events"]
                if event.get("classification") in ("fact", "claim")}
    checks["scenario_clues_required"] = len(required)
    checks["scenario_clues_reached"] = len(required & observed)
    if required - observed:
        differences.append({"missing_clue_sources": sorted(required - observed)})
    checks["canonical_truth_changed"] += case["truth"] != original_truth

    events = state["events"]
    inspect_events(events, case, checks)
    distribution = Counter(task["status"] for task in state["tasks"].values())
    for event in events:
        if event["kind"] == "declined":
            distribution["declined"] += 1
        if event["kind"] == "decision" and event["result"].get("proposal") == "clarify":
            distribution["clarification"] += 1
    model = deepcopy(state["model"])
    model["attempt_failure_rate"] = fraction(
        sum(row.get("status") != "ok" for row in model.get("audit", []) if row.get("attempt")),
        model.get("attempts", 0),
    )
    return {"case": scenario["case"], "seed": scenario["seed"], "input_relations": scenario.get("relations", []),
            "metrics": dict(checks), "task_distribution": dict(distribution), "model": model,
            "scenario_differences": differences, "step_wall_ms": durations, "turns": replies}


def illegal_control(scenario):
    case = load_case(scenario["case"])
    state = new_state(case)
    step = next(step for step in scenario["steps"] if step.get("task") == "completed")

    class InvalidPlan(Decisions):
        def choose(self, purpose, view, candidates, fallback):
            if purpose == "plan":
                return "outside-advertised-candidates", "rules"
            return super().choose(purpose, view, candidates, fallback)

    Dialogue(case, state, InvalidPlan("mock")).submit("test-illegal", step["actor"], step["text"])
    blocked = any(event["kind"] == "rejected" and event["result"].get("status") == "illegal_candidate"
                  for event in state["events"])
    effects = {"accepted", "object_read", "private_question", "private_message", "report"}
    return blocked and not state["tasks"] and not any(event["kind"] in effects for event in state["events"])


def evaluate(scenarios, mode, attempt_limit):
    budget = {"limit": attempt_limit, "used": 0}
    results = [run_scenario(scenario, mode, budget) for scenario in scenarios]
    controls = {case: illegal_control(next(s for s in scenarios if s["case"] == case))
                for case in sorted({scenario["case"] for scenario in scenarios})}
    total = Counter()
    distribution = Counter()
    for result in results:
        total.update(result["metrics"])
        distribution.update(result["task_distribution"])
    guardrails = ("role_knowledge_overreach", "private_model_exposure", "private_player_exposure",
                  "invalid_event_links", "duplicate_event_ids", "missing_sources", "fact_claim_errors",
                  "duplicate_settlements", "event_limit_exceeded", "verdict_errors", "debrief_errors", "canonical_truth_changed",
                  "public_share_errors", "premature_answer_exposure", "replay_or_assist_model_attempts")
    passed = all(controls.values()) and not any(total[key] for key in guardrails)
    if mode in ("mock", "rules"):
        passed = passed and not any(result["scenario_differences"] for result in results)
    else:
        passed = (passed and total["real_private_contact_chains_with_followup"] > 0
                  and all(result["model"].get("attempts", 0) > 0 for result in results)
                  and budget["used"] <= attempt_limit)
    return {"driver": mode, "passed": passed, "scenario_count": len(results),
            "provider_attempt_limit": attempt_limit if mode == "llm" else 0, "provider_attempts": budget["used"],
            "legal_action_rate": fraction(total["legal_action_proposals"], total["action_proposals"]),
            "illegal_action_interception_rate": fraction(sum(controls.values()), len(controls)),
            "source_and_cause_integrity_rate": fraction(total["sources_checked"] + total["event_links_checked"]
                                                        - total["missing_sources"] - total["invalid_event_links"],
                                                        total["sources_checked"] + total["event_links_checked"]),
            "case_completion_rate": fraction(total["solved"], len(results)),
            "scenario_clue_reach_rate": fraction(total["scenario_clues_reached"], total["scenario_clues_required"]),
            "verdict_correctness_rate": fraction(total["verdicts_checked"] - total["verdict_errors"],
                                                 total["verdicts_checked"]),
            "task_distribution": dict(distribution), "metrics": dict(total),
            "illegal_action_controls": controls, "scenarios": results}


def compare_evidence_reactions(mode, attempt_limit):
    case = load_case("example_4")
    text = "请看遗失的宫闱秘录。"
    evidence = "evidence_manuscript_missing"
    actors = ("太平公主", "御史大夫", "张昌宗")
    budget = {"limit": attempt_limit, "used": 0}
    rows = []
    for actor in actors:
        state = new_state(case)
        checks = Counter()
        dialogue = Dialogue(case, state, Probe(mode, state, budget, checks))
        dialogue.submit("same-evidence", actor, text, evidence)
        events = state["events"]
        inspect_events(events, case, checks)
        decision = next((event for event in events if event["kind"] == "decision"
                         and event["result"]["purpose"] == "reaction"), None)
        role = case["roles"][actor]
        rows.append({"actor": actor, "goal": role["goal"], "motivation": role.get("motivation"),
                     "relationships": role["relations"], "knowledge_ids": role["knowledge"],
                     "reaction": decision["result"]["proposal"] if decision else None,
                     "driver": decision["driver"] if decision else None,
                     "events": [{key: event[key] for key in ("id", "kind", "actor", "recipient", "source", "cause")}
                                for event in events],
                     "model": state["model"], "checks": dict(checks)})
    comparable = all(row["driver"] == mode for row in rows)
    distinct = len({row["reaction"] for row in rows if row["reaction"]})
    guardrails = ("invalid_event_links", "role_knowledge_overreach", "private_model_exposure", "fact_claim_errors")
    checks_passed = not any(row["checks"].get(key, 0) for row in rows for key in guardrails)
    return {"driver": mode, "passed": comparable and distinct >= 2 and checks_passed,
            "case": case["id"], "same_input": text, "evidence": evidence,
            "provider_attempt_limit": attempt_limit, "provider_attempts": budget["used"], "roles": rows}


def main():
    scenarios = json.loads(FIXTURES.read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver", choices=("mock", "rules", "llm"), default="mock")
    parser.add_argument("--case", choices=sorted({scenario["case"] for scenario in scenarios}))
    parser.add_argument("--seed", action="append", choices=[scenario["seed"] for scenario in scenarios],
                        help="Repeat to run only the selected fixed scenarios.")
    parser.add_argument("--contrast", action="store_true", help="Present the same evidence to three Palace roles.")
    parser.add_argument("--max-provider-attempts", type=int, help="Required live evaluation budget (1–100).")
    parser.add_argument("--output", type=Path, help="Write the redacted report as JSON.")
    args = parser.parse_args()
    if args.driver == "llm":
        from settings import API_KEY, INFERENCE_SERVICE
        if not 1 <= (args.max_provider_attempts or 0) <= 100:
            parser.error("Live evaluation requires an explicit --max-provider-attempts of 1–100.")
        if INFERENCE_SERVICE != "deepseek" or not API_KEY:
            parser.error("Live evaluation requires the server's authorized DeepSeek configuration.")

    if args.case:
        scenarios = [scenario for scenario in scenarios if scenario["case"] == args.case]
    if args.seed:
        scenarios = [scenario for scenario in scenarios if scenario["seed"] in args.seed]
    if not scenarios:
        parser.error("No scenario matches the requested case and seeds.")
    if args.contrast:
        if args.case or args.seed:
            parser.error("--contrast always runs all three fixed Palace roles.")
        result = compare_evidence_reactions(args.driver, args.max_provider_attempts or 0)
    else:
        result = evaluate(scenarios, args.driver, args.max_provider_attempts or 0)
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
        summary = {key: value for key, value in result.items() if key not in {"scenarios", "roles"}}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(output, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
