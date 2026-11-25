"""Score fixed utterances through the game's actual intent projection."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from npc_decisions import Decisions, ModelRequired
from npc_dialogue import Dialogue, load_case, new_state


def assess(mode, budget):
    with Path(__file__).with_name("intent_samples.tsv").open(encoding="utf-8") as source:
        samples = list(csv.DictReader(source, delimiter="\t"))
    runtime = {}
    rows = []
    for sample in samples:
        if mode == "llm-required" and runtime.get("attempts", 0) + 2 > budget:
            rows.append({**sample, "actual": None, "driver": None, "error": "evaluation_budget"})
            continue
        case = load_case(sample["case"])
        state = new_state(case)
        driver = Decisions(mode, runtime=runtime)
        game = Dialogue(case, state, driver)
        candidates, context = game.intent_options(sample["actor"])
        view = {**game._view(sample["actor"]), **context, "text": sample["text"]}
        try:
            actual, origin = driver.choose("intent", view, candidates, "chat")
            rows.append({**sample, "actual": actual, "driver": origin,
                         "model_candidate": runtime["audit"][-1].get("candidate_id") if origin == "llm" else None})
        except ModelRequired as exc:
            rows.append({**sample, "actual": None, "driver": None, "error": exc.status})
    mistakes = [row for row in rows if row["expected"] != row["actual"]]
    correct = len(samples) - len(mistakes)
    errors = Counter(f"{row['expected']} → {row['actual']}" for row in mistakes)
    unsafe = [row for row in mistakes if (row["actual"] or "").startswith("delegate:")]
    live_failed = mode == "llm-required" and any(row["status"] != "ok" for row in runtime.get("audit", []))
    result = {"mode": mode, "passed": correct / len(samples) >= 0.95 and not unsafe and not live_failed,
              "correct": correct, "total": len(samples), "accuracy": round(correct / len(samples), 4),
              "unsafe_delegations": unsafe, "confusion": dict(errors), "mistakes": mistakes,
              "budget": budget, "rows": rows, "model": runtime}
    if mode == "llm-required":
        result["raw_model_correct"] = sum(row.get("model_candidate") == row["expected"] for row in rows)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("mock", "rules", "llm-required"), default="mock")
    parser.add_argument("--max-attempts", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "llm-required":
        from settings import INFERENCE_SERVICE, MODEL
        if INFERENCE_SERVICE != "deepseek" or MODEL != "deepseek-flash" or not 1 <= args.max_attempts <= 72:
            parser.error("Use configured DeepSeek Flash and a budget between 1 and 72 attempts.")
    result = assess(args.mode, args.max_attempts)
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key not in ("rows", "model")},
                     ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
