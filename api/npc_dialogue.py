"""Case-driven dialogue, with server-owned actions and attributed observations."""
import json
import time
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from npc_case_data import validate_case
from npc_decisions import Decisions

PLAYER = "$player"
PARTY = "$party"
CASE_DIR = Path(__file__).with_name("npc_cases")
TASK_LIFETIME_SECONDS = 15 * 60
MAX_SEAT_COST = 30
MAX_PENDING_TASKS = 3
MAX_REACTION_COST = 20


@lru_cache
def load_case(case_id: str) -> dict | None:
    # Look up a packaged case by name. Requests cannot provide a filesystem path.
    if not case_id or not all(c.isascii() and (c.isalnum() or c in "_-") for c in case_id):
        return None
    path = CASE_DIR / f"{case_id}.json"
    if not path.is_file():
        return None
    return validate_case(json.loads(path.read_text(encoding="utf-8")), expected_id=case_id)


def new_player(case: dict, name: str, first_event: int = 0) -> dict:
    return {
        "name": name,
        "first_event": first_event,
        "evidence": {key: None for key, item in case["evidence"].items() if item.get("initial", True)},
        "pending": {},
        "spent": 0,
        "solved": False,
    }


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
        "events": [], "tasks": {}, "turns": {},
        "players": {PLAYER: new_player(case, "调查者")},
        "model": {},
    }


class Dialogue:
    def __init__(self, case: dict, state: dict, decisions=None, *, player=PLAYER):
        self.case = case
        self.state = state
        if "players" not in state:
            host = new_player(case, "调查者")
            host["pending"] = state.pop("pending", {})
            state["players"] = {PLAYER: host}
        self.player = player
        self.seat = state["players"][player]
        budget = state.setdefault("model", {})
        self.initial_fallbacks = budget.get("fallbacks", 0)
        self.decisions = decisions if decisions is not None else Decisions(runtime=budget)

    def register_player(self, player_id, name):
        players = self.state["players"]
        names = set(self.case["roles"]) | {seat["name"] for seat in players.values()}
        if player_id in players or name.casefold() in {item.casefold() for item in names}:
            raise ValueError("这个调查席位或姓名已存在")
        players[player_id] = new_player(self.case, name, len(self.state["events"]))

    @staticmethod
    def _turn_view(turn):
        return {key: value for key, value in turn.items() if key not in ("player", "event_id")}

    def public_state(self) -> dict:
        return {
            "turns": [self._turn_view(turn) for turn in self.state["turns"].values()
                      if turn.get("player", PLAYER) == self.player],
            "tasks": [self._task_view(task) for task in self.state["tasks"].values()
                      if task["requester"] == self.player],
        }

    @staticmethod
    def _task_view(task):
        return {key: task[key] for key in ("id", "actor", "status", "turn_id")}

    def _event(self, kind, actor, recipient, source, audience, result, cause=None, driver=None):
        event = {
            "id": uuid4().hex,
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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

    def _source_name(self, source):
        item = self.case["evidence"].get(source) or self.case["records"].get(source) or self.case["topics"].get(source)
        return (item.get("name") or item.get("label")) if item else None

    def _view(self, actor):
        role = self.state["roles"][actor]
        definition = self.case["roles"][actor]
        recent = [e for e in self.state["events"] if actor in e["audience"]][-8:]
        return {
            "actor": actor,
            "identity": definition.get("identity", actor),
            "motivation": definition.get("motivation", role["goal"]),
            "goal": role["goal"],
            "relations": dict(role["relations"]),
            "knowledge": [
                {"id": key, "source_event": event, "kind": self.case["records"][key]["kind"],
                 "text": self.case["records"][key]["text"]}
                for key, event in role["known"].items()
            ],
            "beliefs": deepcopy(role["beliefs"]),
            "events": deepcopy(recent),
            "active_tasks": [
                {"topic": task["topic"], "action": task["authorization"]}
                for task in self.state["tasks"].values()
                if task["actor"] == actor and task["status"] == "accepted"
                and task.get("expires_at", float("inf")) > time.time()
            ],
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
        driver = self._display_driver(driver)
        turn = {"id": request_id, "actor": actor, "text": text, "reply": reply, "driver": driver,
                "player": self.player}
        if self.state["events"]:
            event = self.state["events"][-1]
            if self.player in event["audience"]:
                turn.update(source=event["source"], source_name=self._source_name(event["source"]),
                            classification=event["result"].get("classification"), event_id=event["id"])
        self.state["turns"][request_id] = turn
        outcome = {"handled": True, "reply": reply, "driver": driver, "turn": self._turn_view(turn)}
        if task:
            outcome["task"] = self._task_view(task)
        return outcome

    def _display_driver(self, driver):
        if driver == "rules" and self.state["model"].get("fallbacks", 0) > self.initial_fallbacks:
            return "fallback"
        return driver

    def _allows(self, actor, action):
        if actor not in action["roles"]:
            return False
        if action["kind"] == "tell":
            return self._may_disclose(actor, action["record"])
        return action["kind"] in ("ask", "inspect")

    def _may_disclose(self, actor, record_id):
        return (record_id in self.state["roles"][actor]["known"]
                and record_id in self.case["roles"][actor]["disclosure"])

    def _missing(self, actor, action):
        shown = self._presentations(actor)
        return [self.case["evidence"][key]["name"] for key in action.get("requires", []) if key not in shown]

    def _presentations(self, actor):
        role = self.state["roles"][actor]
        presentations = role.setdefault("presentations", {PLAYER: dict(role["shown"])})
        return presentations.get(self.player, {})

    def _options(self, actor, action_ids):
        return [
            {"id": key, "label": self.case["actions"][key]["label"]}
            for key in action_ids
            if self._allows(actor, self.case["actions"][key]) and not self._missing(actor, self.case["actions"][key])
        ]

    def submit(self, request_id, actor, text, evidence=None):
        if self.seat["solved"]:
            raise ValueError("你已结案，可以继续查看复盘")
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
                {"id": f"inquire:{topic['id']}", "label": f"直接询问角色所知：{topic['label']}"},
                {"id": f"followup:{topic['id']}", "label": f"询问进展：{topic['label']}"},
                {"id": f"receipt:{topic['id']}", "label": f"询问收到过什么消息或联系：{topic['label']}"},
                {"id": f"origin:{topic['id']}", "label": f"追问来源：{topic['label']}"},
            ])
        pending_by_actor = self.seat["pending"]
        pending = pending_by_actor.get(actor)
        # The most recent player exchange provides the referent of “查到了吗” or “谁告诉你的”.
        observed = next(
            ([self._topic(event["source"])] for event in reversed(self.state["events"])
             if actor in event["audience"] and self.player in event["audience"] and self._topic(event["source"])),
            [],
        )
        proposal, decision, driver = self._choose(
            "intent", actor, None, None, candidates, "chat",
            text=text, topics=topics, pending_topic=pending, observed_topics=observed,
        )
        if proposal == "chat":
            self._event("conversation", self.player, actor, None, (self.player, actor),
                        {"text": text, "classification": "claim"}, decision)
            return {"handled": False}
        if proposal is None:
            return self._reply(request_id, actor, text, "我没能确认你的要求。请再说清楚要找谁、核查什么。", driver)
        if proposal == "clarify":
            pending_by_actor[actor] = pending or ""
            return self._reply(request_id, actor, text, "你想让我联系哪位人物，或核对哪一份材料？", driver)
        kind, topic = proposal.split(":", 1)
        pending_by_actor.pop(actor, None)
        if kind == "delegate":
            return self._delegate(request_id, actor, text, topic, decision, driver)
        if kind == "inquire":
            reply = self._inquire(actor, topic, decision)
        else:
            reply = self._followup(actor, topic, kind, decision)
        return self._reply(request_id, actor, text, reply, driver)

    def _delegate(self, request_id, actor, text, topic, cause, intent_driver):
        role = self.state["roles"][actor]
        item = self.case["topics"][topic]
        request = self._event("delegation", self.player, actor, topic, (self.player, actor), {"text": text}, cause)
        allowed = [self.case["actions"][key] for key in item["options"]
                   if self._allows(actor, self.case["actions"][key])]
        options = self._options(actor, item["options"])
        willing = role["relations"].get(self.player, role["relations"].get(PLAYER, 0)) >= 0
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
        if intent_driver == "rules":
            driver = "rules"
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
            self._event("declined", actor, self.player, topic, (self.player, actor), {"text": reply}, decision)
            return self._reply(request_id, actor, text, reply, driver)
        action = self.case["actions"][choice]
        own_tasks = [task for task in self.state["tasks"].values() if task["requester"] == self.player]
        previous = next((task for task in reversed(own_tasks) if task["actor"] == actor
                         and task["authorization"] == choice and task["status"] == "completed"), None)
        if previous:
            report = next(event for event in self.state["events"] if event["id"] == previous["result"])
            reply = report["result"]["text"]
            self._event("statement", actor, self.player, report["source"], (actor, self.player),
                        {"text": reply, "classification": "claim"}, report["id"])
            return self._reply(request_id, actor, text, reply, driver)
        now = time.time()
        pending = [task for task in own_tasks if task["status"] == "accepted"
                   and task.get("expires_at", float("inf")) > now]
        if any(task["actor"] == actor and task["authorization"] == choice for task in pending):
            reply = "这件事我已经答应查了，等原委托的回报吧。"
            return self._reply(request_id, actor, text, reply, driver)
        cost = action.get("cost", 1)
        if len(pending) >= MAX_PENDING_TASKS or self.seat["spent"] + cost > MAX_SEAT_COST:
            reply = "手头的调查安排已经满了。先核对已有回报或直接问当事人。"
            self._event("declined", actor, self.player, topic, (self.player, actor),
                        {"text": reply, "reason": "capacity"}, decision)
            return self._reply(request_id, actor, text, reply, driver)
        self.seat["spent"] += cost
        acknowledgement = f"好，我去{action['label']}。"
        task_id = uuid4().hex
        accepted = self._event("accepted", actor, self.player, topic, (self.player, actor),
                               {"task": task_id, "action": choice, "text": acknowledgement, "cost": cost}, decision)
        task = {
            "id": task_id, "turn_id": request_id, "requester": self.player, "actor": actor,
            "target": action["target"], "authorization": choice, "topic": topic, "status": "accepted",
            "cause": accepted, "acknowledgement": acknowledgement, "driver": self._display_driver(driver), "result": None,
            "expires_at": now + TASK_LIFETIME_SECONDS,
        }
        self.state["tasks"][task_id] = task
        return self._reply(request_id, actor, text, acknowledgement, driver, task)

    def resume(self, task_id):
        task = self.state["tasks"].get(task_id)
        if task is None or task["requester"] != self.player:
            raise KeyError(task_id)
        turn = self.state["turns"][task["turn_id"]]
        if task["status"] != "accepted":
            return {"handled": True, "reply": turn["reply"], "driver": turn.get("driver", task["driver"]),
                    "turn": self._turn_view(turn), "task": self._task_view(task)}
        if self.seat["solved"] or time.time() >= task.get("expires_at", float("inf")):
            status = "cancelled" if self.seat["solved"] else "expired"
            reason = "案件已经结案，未执行这项委托。" if self.seat["solved"] else "这项委托已过期，未执行。"
            result = self._failure(task["actor"], task["topic"], task["cause"], reason)
            result["status"] = status
        else:
            result = self._execute(task["actor"], task["authorization"], task["cause"])
        reply = task["acknowledgement"] + "\n\n" + result["text"]
        report = self._event("report", task["actor"], self.player, result["source"] or task["topic"],
                             (task["actor"], self.player),
                             {"task": task_id, "status": result["status"], "text": result["text"],
                              "classification": result.get("classification"), "topic": task["topic"]}, result["event"])
        task.update(status=result["status"], result=report)
        driver = "rules" if result.get("driver") == "rules" else task["driver"]
        outcome = self._reply(turn["id"], task["actor"], turn["text"], reply, driver, task)
        if result["status"] == "completed":
            self._grant_evidence(task, report)
        return outcome

    def _grant_evidence(self, task, cause):
        inventory = self.seat["evidence"]
        for evidence_id in self.case["actions"][task["authorization"]].get("grants", []):
            if evidence_id not in inventory:
                evidence = self.case["evidence"][evidence_id]
                inventory[evidence_id] = self._event(
                    "evidence_acquired", task["actor"], self.player, evidence_id, (self.player,),
                    {"text": evidence["text"], "classification": "fact"}, cause,
                )

    def _show(self, request_id, actor, text, evidence_id):
        evidence = self.case["evidence"].get(evidence_id)
        if evidence is None or evidence_id not in self.seat["evidence"]:
            status = "unknown_evidence" if evidence is None else "not_held"
            self._event("rejected", self.player, actor, evidence_id, (), {"status": status})
            reply = "这份材料不在本案可核查的证物中。" if evidence is None else "这份材料尚未取得，不能出示。"
            return self._reply(request_id, actor, text, reply, "rules")
        role = self.state["roles"][actor]
        if evidence_id in self._presentations(actor):
            return self._reply(request_id, actor, text, "这份材料你已经给我看过了。", "rules")
        previously_seen = evidence_id in role["shown"]
        topic = evidence["topic"]
        shown = self._event("show", self.player, actor, evidence_id, (self.player, actor),
                            {"text": evidence["text"], "classification": "fact"}, self.seat["evidence"][evidence_id])
        role["presentations"].setdefault(self.player, {})[evidence_id] = shown
        role["shown"].setdefault(evidence_id, shown)
        reply = evidence.get("reply", f"我看过{evidence['name']}了，会把它作为一条待查线索。")
        if previously_seen:
            return self._reply(request_id, actor, text, reply, "rules")
        options = self._options(actor, self.case["reactions"].get(topic, {}).get(actor, []))
        fallback = options[0]["id"] if options and topic in role["interests"] else "hold"
        choice, decision, driver = self._choose(
            "reaction", actor, shown, topic,
            [{"id": "hold", "label": "保留材料"}, {"id": "defer", "label": "暂缓行动"}] + options, fallback,
        )
        if choice not in (None, "hold", "defer"):
            cost = self.case["actions"][choice].get("cost", 1)
            spent = self.state.get("reaction_spent", 0)
            if spent + cost > MAX_REACTION_COST:
                self._event("rejected", actor, None, topic, (), {"status": "world_capacity"}, decision)
            else:
                self.state["reaction_spent"] = spent + cost
                result = self._execute(actor, choice, decision)
                if result.get("driver") == "rules":
                    driver = "rules"
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
        if asking and self._may_disclose(target, record_id):
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
        choice, decision, driver = self._choose("response", target, contact, topic, choices, fallback)
        receipt = self._event(
            "reception", target, actor, topic, (target,),
            {"stance": choice, "contact": contact}, decision,
        )
        result = {"status": "completed", "source": topic, "event": receipt, "driver": driver}
        if choice is None:
            return {**self._failure(actor, topic, receipt, f"{target}没有给出可以确认的回应。"), "driver": driver}
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
        return {**self._failure(actor, topic, receipt, f"我联系了{target}，对方没有提供这件事的内容。"),
                "driver": driver}

    def _inquire(self, actor, topic, cause):
        role = self.state["roles"][actor]
        replies = []
        if role["relations"].get(self.player, role["relations"].get(PLAYER, 0)) >= 0:
            for record_id in self.case["roles"][actor]["disclosure"]:
                record = self.case["records"][record_id]
                if record["topic"] != topic or not self._may_disclose(actor, record_id):
                    continue
                reply = f"《{record['name']}》中的说法是“{record['text']}”"
                self._event("statement", actor, self.player, record_id, (actor, self.player),
                            {"text": reply, "classification": "claim", "original_source": record["name"]},
                            role["known"][record_id] or cause)
                replies.append(reply)
        if replies:
            return "\n".join(replies)
        reply = "这件事我没有可以直接告诉你的记录。"
        self._event("statement", actor, self.player, topic, (actor, self.player),
                    {"text": reply, "classification": "claim"}, cause)
        return reply

    def _followup(self, actor, topic, kind, cause):
        configuration = self.case["followups"].get(topic, {}).get(actor, {})
        receipt = None
        report = None
        receipt_visible = False
        for event in reversed(self.state["events"]):
            if event["actor"] != actor:
                continue
            if (receipt is None and configuration.get("receipt") and event["kind"] == "reception"
                    and event["source"] == topic):
                receipt = event
                receipt_visible = receipt["result"]["stance"] in ("accept", "question", "disclose")
                if receipt_visible or kind == "receipt":
                    break
            if (report is None and kind != "receipt" and event["kind"] == "report" and self.player in event["audience"]
                    and event["result"]["topic"] == topic):
                report = event
                if kind == "followup":
                    break

        parent = cause
        public_receipt = False
        if receipt_visible:
            parent = receipt["id"]
            if kind == "origin":
                disclosed = any(event["kind"] == "statement" and event["cause"] == parent
                                and event["result"].get("receipt") and self.player in event["audience"]
                                for event in self.state["events"])
                if configuration.get("origin_requires_statement") and not disclosed:
                    reply = "请先问我这方面收到过什么消息。"
                else:
                    reply = f"据我亲历，是{receipt['recipient']}联系我的。这是我的陈述。"
            elif receipt["result"]["stance"] == "question":
                public_receipt = True
                reply = configuration.get("question", "我收到一项说法，仍需核对。你可以向我追问是从哪儿来的。")
            elif receipt["result"]["stance"] == "accept":
                public_receipt = True
                reply = configuration.get("accept", "有人提供了线索，我愿意暂时采信。你可以再问我来源。")
            else:
                public_receipt = True
                reply = configuration.get("disclose", "有人托我查过。你可以再问我是谁提出的。")
        elif report is not None:
            parent = report["id"]
            reply = report["result"]["text"]
        else:
            reply = configuration.get("baseline", "我目前没有可以转述的这方面进展。")
        # Even when an underlying report points to a record, this event is a character's statement.
        self._event("statement", actor, self.player, topic, (actor, self.player),
                    {"text": reply, "classification": "claim", "receipt": public_receipt}, parent)
        return reply

    def _visible(self):
        return [event for event in self.state["events"]
                if self.player in event["audience"] or PARTY in event["audience"]]

    def _event_view(self, event, visible_ids, *, earlier=False):
        actor = self.state["players"].get(event["actor"], {}).get("name", event["actor"])
        shared = PARTY in event["audience"]
        view = "prior_public" if earlier else ("public" if shared else "private")
        observer = None
        if event["kind"] == "show" and event["recipient"] in self.case["roles"]:
            observer = event["recipient"]
        elif event["kind"] in ("statement", "report"):
            view = "npc_statement" if event["kind"] == "statement" else view
            observer = event["actor"]
        source = event["source"]
        return {
            "id": event["id"], "kind": event["kind"], "actor": actor, "source": source,
            "source_name": self._source_name(source),
            "cause": event["cause"] if event["cause"] in visible_ids else None,
            "time": event.get("time"), "text": event["result"].get("text", ""),
            "classification": event["result"].get("classification"), "driver": event["driver"], "view": view,
            "observer": observer,
        }

    def room(self):
        inventory = self.seat["evidence"]
        players = [{"id": key, "name": seat["name"]} for key, seat in self.state["players"].items()]
        public = [event for event in self.state["events"] if PARTY in event["audience"]]
        public_ids = {event["id"] for event in public}
        return {
            "self": {"id": self.player, "name": self.seat["name"]}, "players": players,
            "evidence": list(inventory), "solved": self.seat["solved"],
            "evidence_details": [
                {"id": key, **{name: self.case["evidence"][key][name]
                               for name in ("name", "text", "category", "importance")
                               if name in self.case["evidence"][key]}}
                for key in inventory
            ],
            "public": [self._event_view(event, public_ids) for event in public],
        }

    def share(self, turn_id):
        turn = self.state["turns"].get(turn_id)
        if turn is None or turn.get("player", PLAYER) != self.player:
            raise KeyError(turn_id)
        events = self.state["events"]
        shared = next((event for event in events if event["kind"] == "shared"
                       and event["result"]["turn"] == turn_id and event["actor"] == self.player), None)
        if shared is None:
            result = next((event for event in events if event["id"] == turn.get("event_id")
                           and self.player in event["audience"]), None)
            if result is None or result["result"].get("classification") not in ("fact", "claim"):
                raise ValueError("这条回复还没有可公开的线索")
            self._event(
                "shared", self.player, None, result["source"], (PARTY,),
                {"turn": turn_id, "text": result["result"]["text"],
                 "classification": result["result"]["classification"]}, result["id"],
            )
            shared = events[-1]
        # A party response never includes the owner's private parent ID.
        return {"shared": self._event_view(shared, {shared["id"]})}

    def replay(self):
        visible = self._visible()
        ids = {event["id"] for event in visible}
        earlier_ids = {event["id"] for event in self.state["events"][:self.seat.get("first_event", 0)]}
        return {"events": [self._event_view(event, ids, earlier=event["id"] in earlier_ids)
                           for event in visible]}

    def assist(self, level, query=""):
        if level == "answer":
            if not self.seat["solved"]:
                raise ValueError("请先提交正确的结案推理")
            truth = self.case["truth"]
            timeline = "\n".join(f"{item['when']} · {item['event']}" for item in truth["timeline"])
            return {"level": level, "driver": "rules", "text": truth["explanation"] + "\n\n" + timeline}
        if level not in ("summary", "nudge"):
            raise ValueError("未知的提示级别")
        events = [event for event in self._visible()
                  if event["kind"] in ("report", "statement", "shared", "evidence_acquired")
                  and event["result"].get("classification") in ("fact", "claim")]
        lines = []
        for event in events[-5:]:
            prefix = "已核查" if event["result"]["classification"] == "fact" else "待核实的说法"
            record_id = event["source"]
            record = self.case["records"].get(record_id) or self.case["evidence"].get(record_id)
            name = record["name"] if record else self.case["topics"].get(record_id, {}).get("label", "调查回报")
            lines.append(f"{prefix} · {name}\n{event['result']['text']}")
        if level == "summary":
            categories = {}
            for event in events:
                topic = self._topic(event["source"])
                if topic:
                    categories.setdefault(topic, set()).add(event["result"]["classification"])
            review = [self.case["topics"][key]["label"] for key, kinds in categories.items()
                      if kinds == {"fact", "claim"}]
            if review:
                lines.append("可对照记录与口述 · " + "、".join(review))
            return {"level": level, "driver": "rules",
                    "text": "\n\n".join(lines) or "暂时没有可归纳的回报。可以询问人物或浏览已取得的证物。"}
        topics = dict.fromkeys(self._topic(source) for source in (
            *(event["source"] for event in reversed(events)),
            *self.seat["evidence"],
        ))
        candidates = [{"id": key, "label": self.case["topics"][key]["hint"]}
                      for key in topics if key and self.case["topics"][key].get("hint")]
        if not candidates:
            return {"level": level, "driver": "rules", "text": "先问一个能说明案发前后经过的角色。"}
        fallback = candidates[0]["id"]
        proposal, driver = self.decisions.choose(
            "assist", {"observations": lines, "question": query}, candidates, fallback,
        )
        choice = next((option for option in candidates if option["id"] == proposal), None)
        if choice is None:
            self._event("rejected", self.player, None, None, (), {"status": "illegal_hint"}, driver=driver)
            choice, driver = candidates[0], "rules"
        self._event("hint", self.player, None, choice["id"], (self.player,), {"text": choice["label"]}, driver=driver)
        return {"level": level, "driver": self._display_driver(driver), "text": choice["label"]}

    def verdict(self, suspect, motive):
        if self.seat["solved"]:
            return {"correct": True, "message": "你已经结案，可以查看解释。"}
        choices = self.case["verdict"]
        if suspect not in choices["suspects"] or motive not in choices["motives"]:
            raise ValueError("请选择本案的嫌疑人与动机")
        truth = self.case["truth"]
        correct = suspect == truth["suspect"] and motive == truth["motive"]
        message = "推理成立，你已结案。" if correct else "这项推理未能解释全部线索，请继续调查。"
        self._event("verdict", self.player, None, None, (self.player,),
                    {"text": message, "suspect": suspect, "motive": motive, "correct": correct})
        self.seat["solved"] = correct
        return {"correct": correct, "message": message}
