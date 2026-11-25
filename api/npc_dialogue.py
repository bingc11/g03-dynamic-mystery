"""Case-driven dialogue, with server-owned actions and attributed observations."""
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from npc_decisions import Decisions

PLAYER = "$player"
CASE_DIR = Path(__file__).with_name("npc_cases")


@lru_cache
def load_case(case_id: str) -> dict | None:
    # Look up a packaged case by name. Requests cannot provide a filesystem path.
    if not case_id or not all(c.isascii() and (c.isalnum() or c in "_-") for c in case_id):
        return None
    path = CASE_DIR / f"{case_id}.json"
    if not path.is_file():
        return None
    case = json.loads(path.read_text(encoding="utf-8"))
    if case["id"] != case_id:
        raise ValueError(f"Case ID does not match {path.name}")
    return case


def new_state(case: dict) -> dict:
    return {
        "roles": {
            name: {
                "goal": role["goal"],
                "interests": role["interests"],
                "relations": dict(role["relations"]),
                "known": {key: None for key in role["knowledge"]},
                "shown": {},
                "beliefs": {},
            }
            for name, role in case["roles"].items()
        },
        "events": [], "tasks": {}, "turns": {}, "pending": {},
    }


class Dialogue:
    def __init__(self, case: dict, state: dict, decisions=None):
        self.case = case
        self.state = state
        self.decisions = decisions if decisions is not None else Decisions()

    def public_state(self) -> dict:
        return {
            "turns": list(self.state["turns"].values()),
            "tasks": [self._task_view(task) for task in self.state["tasks"].values()],
        }

    @staticmethod
    def _task_view(task):
        return {key: task[key] for key in ("id", "actor", "status", "turn_id")}

    def _event(self, kind, actor, recipient, source, audience, result, cause=None, driver=None):
        event = {
            "id": uuid4().hex,
            "kind": kind,
            "actor": actor,
            "recipient": recipient,
            "source": source,
            "audience": list(dict.fromkeys(audience)),
            "cause": cause,
            "result": result,
            "driver": driver,
        }
        self.state["events"].append(event)
        return event["id"]

    def _topic(self, source):
        if source in self.case["topics"]:
            return source
        item = self.case["records"].get(source) or self.case["evidence"].get(source)
        return item["topic"] if item else None

    def _view(self, actor):
        role = self.state["roles"][actor]
        recent = [e for e in self.state["events"] if actor in e["audience"]][-8:]
        return {
            "actor": actor,
            "goal": role["goal"],
            "relations": dict(role["relations"]),
            "knowledge": [
                {"id": key, "source_event": event, "kind": self.case["records"][key]["kind"],
                 "text": self.case["records"][key]["text"]}
                for key, event in role["known"].items()
            ],
            "beliefs": deepcopy(role["beliefs"]),
            "events": deepcopy(recent),
        }

    def _choose(self, purpose, actor, cause, source, candidates, fallback, **context):
        proposal, driver = self.decisions.choose(purpose, {**self._view(actor), **context}, candidates, fallback)
        legal = next((choice for choice in candidates if choice["id"] == proposal), None)
        decision = self._event(
            "decision" if legal else "rejected", actor, None, source, (), {
                "purpose": purpose, "proposal": proposal if legal else None,
                "status": "selected" if legal else "illegal_candidate",
            }, cause, driver,
        )
        return (proposal if legal else None), decision, driver

    def _reply(self, request_id, actor, text, reply, driver, task=None):
        turn = {"id": request_id, "actor": actor, "text": text, "reply": reply}
        self.state["turns"][request_id] = turn
        outcome = {"handled": True, "reply": reply, "driver": driver, "turn": turn}
        if task:
            outcome["task"] = self._task_view(task)
        return outcome

    def _allows(self, actor, action):
        if actor not in action["roles"]:
            return False
        if action["kind"] == "tell":
            return (
                action["record"] in self.state["roles"][actor]["known"]
                and action["record"] in self.case["roles"][actor]["disclosure"]
            )
        return action["kind"] in ("ask", "inspect")

    def _missing(self, actor, action):
        shown = self.state["roles"][actor]["shown"]
        return [self.case["evidence"][key]["name"] for key in action.get("requires", []) if key not in shown]

    def _options(self, actor, action_ids):
        return [
            {"id": key, "label": self.case["actions"][key]["label"]}
            for key in action_ids
            if self._allows(actor, self.case["actions"][key]) and not self._missing(actor, self.case["actions"][key])
        ]

    def submit(self, request_id, actor, text, evidence=None):
        if actor not in self.state["roles"]:
            raise ValueError("案件中没有这个调查对象")
        if evidence is not None:
            return self._show(request_id, actor, text, evidence)
        topics = [{"id": key, "label": topic["label"], "aliases": topic["aliases"]}
                  for key, topic in self.case["topics"].items()]
        candidates = [{"id": "chat", "label": "普通对话"}, {"id": "clarify", "label": "委托目标需要澄清"}]
        for topic in topics:
            candidates.extend([
                {"id": f"delegate:{topic['id']}", "label": f"委托处理：{topic['label']}"},
                {"id": f"followup:{topic['id']}", "label": f"询问进展：{topic['label']}"},
                {"id": f"origin:{topic['id']}", "label": f"追问来源：{topic['label']}"},
            ])
        pending = self.state["pending"].get(actor)
        # The most recent player exchange provides the referent of “查到了吗” or “谁告诉你的”.
        observed = next(
            ([self._topic(event["source"])] for event in reversed(self.state["events"])
             if actor in event["audience"] and PLAYER in event["audience"] and self._topic(event["source"])),
            [],
        )
        proposal, decision, driver = self._choose(
            "intent", actor, None, None, candidates, "chat",
            text=text, topics=topics, pending_topic=pending, observed_topics=observed,
        )
        if proposal == "chat":
            return {"handled": False}
        if proposal is None:
            return self._reply(request_id, actor, text, "我没能确认你的要求。请再说清楚要找谁、核查什么。", driver)
        if proposal == "clarify":
            self.state["pending"][actor] = pending or ""
            return self._reply(request_id, actor, text, "你想让我联系哪位人物，或核对哪一份材料？", driver)
        kind, topic = proposal.split(":", 1)
        self.state["pending"].pop(actor, None)
        if kind == "delegate":
            return self._delegate(request_id, actor, text, topic, decision)
        reply = self._followup(actor, topic, kind == "origin", decision)
        return self._reply(request_id, actor, text, reply, driver)

    def _delegate(self, request_id, actor, text, topic, cause):
        role = self.state["roles"][actor]
        item = self.case["topics"][topic]
        request = self._event("delegation", PLAYER, actor, topic, (PLAYER, actor), {"text": text}, cause)
        allowed = [self.case["actions"][key] for key in item["options"]
                   if self._allows(actor, self.case["actions"][key])]
        options = self._options(actor, item["options"])
        willing = role["relations"].get(PLAYER, 0) >= 0
        fallback = options[0]["id"] if options and willing and topic in role["interests"] else "decline"
        candidates = [
            {"id": "decline", "label": "拒绝"},
            {"id": "defer", "label": "这会儿无法答应"},
        ]
        if willing:
            candidates.extend(options)
        choice, decision, driver = self._choose(
            "plan", actor, request, topic, candidates, fallback,
            request={"topic": item["label"], "text": text},
        )
        if choice not in {option["id"] for option in options}:
            if choice is None:
                reply = "我没能确认一条可执行的办法。你可以换个目标再问。"
            elif not willing:
                reply = "我现在还不愿意替你查这件事。"
            elif not allowed:
                alternatives = list(dict.fromkeys(
                    name for key in item["options"] for name in self.case["actions"][key]["roles"]
                    if name != actor and role["relations"].get(name, 0) > 0
                ))
                suggestion = f"你可以去问{alternatives[0]}。" if alternatives else "你可以试着向负责保管的人询问。"
                reply = f"我没有权限替你查{item['label']}。{suggestion}"
            elif not options:
                needed = list(dict.fromkeys(name for action in allowed for name in self._missing(actor, action)))
                reply = "我还缺核查所需的材料。请先给我看：" + "、".join(needed) + "。"
            elif choice == "defer":
                reply = "这会儿我腾不出手。你可以稍后再问我。"
            else:
                reply = "这件事我先不接。你可以直接向当事人了解。"
            self._event("declined", actor, PLAYER, topic, (PLAYER, actor), {"text": reply}, decision)
            return self._reply(request_id, actor, text, reply, driver)
        action = self.case["actions"][choice]
        acknowledgement = f"好，我去{action['label']}。"
        task_id = uuid4().hex
        accepted = self._event("accepted", actor, PLAYER, topic, (PLAYER, actor),
                               {"task": task_id, "action": choice, "text": acknowledgement}, decision)
        task = {
            "id": task_id, "turn_id": request_id, "requester": PLAYER, "actor": actor,
            "target": action["target"], "authorization": choice, "topic": topic, "status": "accepted",
            "cause": accepted, "acknowledgement": acknowledgement, "driver": driver, "result": None,
        }
        self.state["tasks"][task_id] = task
        return self._reply(request_id, actor, text, acknowledgement, driver, task)

    def resume(self, task_id):
        task = self.state["tasks"].get(task_id)
        if task is None:
            raise KeyError(task_id)
        turn = self.state["turns"][task["turn_id"]]
        if task["status"] != "accepted":
            return self._reply(turn["id"], task["actor"], turn["text"], turn["reply"], task["driver"], task)
        result = self._execute(task["actor"], task["authorization"], task["cause"])
        reply = task["acknowledgement"] + "\n\n" + result["text"]
        report = self._event("report", task["actor"], PLAYER, result["source"] or task["topic"], (task["actor"], PLAYER),
                             {"task": task_id, "status": result["status"], "text": result["text"],
                              "classification": result.get("classification"), "topic": task["topic"]}, result["event"])
        task.update(status=result["status"], result=report)
        return self._reply(turn["id"], task["actor"], turn["text"], reply, task["driver"], task)

    def _show(self, request_id, actor, text, evidence_id):
        evidence = self.case["evidence"].get(evidence_id)
        if evidence is None:
            self._event("rejected", PLAYER, actor, None, (), {"status": "unknown_evidence"})
            return self._reply(request_id, actor, text, "这份材料不在本案可核查的证物中。", "rules")
        role = self.state["roles"][actor]
        if evidence_id in role["shown"]:
            return self._reply(request_id, actor, text, "这份材料你已经给我看过了。", "rules")
        topic = evidence["topic"]
        shown = self._event("show", PLAYER, actor, evidence_id, (PLAYER, actor), {"text": evidence["text"]})
        role["shown"][evidence_id] = shown
        options = self._options(actor, self.case["reactions"].get(topic, {}).get(actor, []))
        fallback = options[0]["id"] if options and topic in role["interests"] else "hold"
        choice, decision, driver = self._choose(
            "reaction", actor, shown, topic,
            [{"id": "hold", "label": "保留材料"}, {"id": "defer", "label": "暂缓行动"}] + options, fallback,
        )
        if choice not in (None, "hold", "defer"):
            self._execute(actor, choice, decision)
        reply = evidence.get("reply", f"我看过{evidence['name']}了，会把它作为一条待查线索。")
        return self._reply(request_id, actor, text, reply, driver)

    def _failure(self, actor, source, cause, text):
        event = self._event("action_failed", actor, None, source, (actor,), {"text": text}, cause)
        return {"status": "failed", "source": source, "event": event, "text": text}

    def _execute(self, actor, choice, cause):
        action = self.case["actions"].get(choice)
        if action is None or not self._allows(actor, action) or self._missing(actor, action):
            rejected = self._event("rejected", actor, None, None, (), {"status": "authorization_changed"}, cause)
            return self._failure(actor, None, rejected, "执行时授权或材料条件不再满足，没能完成。")
        if not self.case["roles"][actor].get("availability", True):
            return self._failure(actor, action["topic"], cause, "我现在无法离开，没能完成这次委托。")
        if action["kind"] == "inspect":
            return self._inspect(actor, action["target"], cause)
        return self._contact(actor, action, cause)

    def _inspect(self, actor, record_id, cause):
        record = self.case["records"][record_id]
        if not record.get("available", True):
            return self._failure(actor, record_id, cause, f"我去核对了{record['name']}，当时无法调取原件。")
        event = self._event("object_read", actor, None, record_id, (actor,),
                            {"text": record["text"], "classification": record["kind"]}, cause)
        self.state["roles"][actor]["known"][record_id] = event
        marker = "待核实的说法" if record["kind"] == "claim" else "已核查的记录"
        return {"status": "completed", "source": record_id, "event": event, "classification": record["kind"],
                "text": f"我查阅了《{record['name']}》。{marker}：{record['text']}"}

    def _contact(self, actor, action, cause):
        target, topic = action["target"], action["topic"]
        if not self.case["roles"][target].get("availability", True):
            return self._failure(actor, topic, cause, f"我试着联系{target}，对方当时无法回应。")
        receiver = self.state["roles"][target]
        role = self.case["roles"][target]
        record_id = action["record"]
        record = self.case["records"][record_id]
        asking = action["kind"] == "ask"
        if asking:
            payload = {"topic": topic, "text": action["label"]}
        else:
            payload = {"topic": topic, "text": record["text"], "record": record_id,
                       "prior": self.state["roles"][actor]["known"][record_id], "classification": "claim"}
        contact = self._event("private_question" if asking else "private_message", actor, target, topic,
                              (actor, target), payload, cause)
        trust = receiver["relations"].get(actor, 0)
        # A conversation can change willingness and leads, never the underlying record.
        choices = [{"id": "hide", "label": "保留内容"}, {"id": "refuse", "label": "拒绝继续"}]
        fallback = "refuse" if trust < 0 else "hide"
        if asking and record_id in receiver["known"] and record_id in role["disclosure"]:
            choices.append({"id": "disclose", "label": "向询问者转述已知内容"})
            if trust > 0:
                fallback = "disclose"
        if not asking:
            choices.append({"id": "accept", "label": "暂时采信这项人物主张"})
            if record_id in role["verify"]:
                choices.append({"id": "question", "label": "质疑并等待补充材料"})
            if trust > 0:
                fallback = "accept"
            elif trust == 0 and record_id in role["verify"]:
                fallback = "question"
        choice, decision, _ = self._choose("response", target, contact, topic, choices, fallback)
        receipt = self._event(
            "reception", target, actor, topic, (target,),
            {"stance": choice, "contact": contact}, decision,
        )
        result = {"status": "completed", "source": topic, "event": receipt}
        if choice is None:
            return self._failure(actor, topic, receipt, f"{target}没有给出可以确认的回应。")
        if choice == "disclose":
            claim = self._event("claim", target, actor, record_id, (actor, target), {
                "text": record["text"], "classification": "claim", "original_source": record["name"],
                "prior": receiver["known"][record_id],
            }, receipt)
            self.state["roles"][actor]["beliefs"][claim] = {"state": "heard", "source": record_id}
            return {**result, "source": record_id, "event": claim, "classification": "claim",
                    "text": f"我问过{target}。对方就《{record['name']}》告诉我：{record['text']} 这是对方的说法。"}
        if choice in ("accept", "question"):
            receiver["beliefs"][contact] = {"state": choice, "source": record_id}
            return {**result, "classification": "claim",
                    "text": f"我把《{record['name']}》中知道的情况转告了{target}。"}
        return self._failure(actor, topic, receipt, f"我联系了{target}，对方没有提供这件事的内容。")

    def _followup(self, actor, topic, origin, cause):
        configuration = self.case["followups"].get(topic, {}).get(actor, {})
        receipts = [e for e in self.state["events"] if e["kind"] == "reception" and e["actor"] == actor
                    and e["source"] == topic]
        last = receipts[-1] if receipts and configuration.get("receipt") else None
        previous = next(
            (event for event in reversed(self.state["events"]) if event["kind"] == "report"
             and event["actor"] == actor and event["result"]["topic"] == topic), None,
        )
        parent = cause
        public_receipt = False
        if last is not None and last["result"]["stance"] not in (None, "hide", "refuse"):
            parent = last["id"]
            receipt_disclosed = any(event["kind"] == "statement" and event["cause"] == last["id"]
                                    and event["result"].get("receipt") for event in self.state["events"])
            if origin and configuration.get("origin_requires_statement") and not receipt_disclosed:
                reply = "请先问我这方面收到过什么消息。"
            elif origin:
                reply = f"据我亲历，是{last['recipient']}联系我的。这是我的陈述。"
            elif last["result"]["stance"] == "question":
                public_receipt = True
                reply = configuration.get("question", "我收到一项说法，仍需核对。你可以向我追问是从哪儿来的。")
            elif last["result"]["stance"] == "accept":
                public_receipt = True
                reply = configuration.get("accept", "有人提供了线索，我愿意暂时采信。你可以再问我来源。")
            else:
                public_receipt = True
                reply = configuration.get("disclose", "有人托我查过。你可以再问我是谁提出的。")
        elif previous is not None:
            parent = previous["id"]
            reply = previous["result"]["text"]
        else:
            reply = configuration.get("baseline", "我目前没有可以转述的这方面进展。")
        # Even when an underlying report points to a record, this event is a character's statement.
        self._event("statement", actor, PLAYER, topic, (actor, PLAYER),
                    {"text": reply, "classification": "claim", "receipt": public_receipt}, parent)
        return reply
