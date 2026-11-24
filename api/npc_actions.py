"""A finite, offline rule for the existing palace case. Everything here runs on the server."""
from dataclasses import dataclass
from typing import Callable

MANUSCRIPT = "evidence_manuscript_missing"
CASE = "example_4"
PRINCESS, CENSOR, WITNESS = "太平公主", "御史大夫", "张昌宗"
PLAYER = "调查者"
ROLES = (PRINCESS, CENSOR, WITNESS)
GOALS = {PRINCESS: "核实秘录的登记，保留谈话内容", CENSOR: "核对信息来源", WITNESS: "保留意见"}


@dataclass(frozen=True)
class Event:
    seq: int
    cause: int | None
    kind: str
    actor: str
    audience: tuple[str, ...]
    source: str
    text: str


@dataclass(frozen=True)
class Observation:
    cause: int
    source: str
    kind: str
    text: str


@dataclass(frozen=True)
class Choice:
    action: str
    target: str
    source: str


@dataclass(frozen=True)
class View:
    actor: str
    goal: str
    memory: tuple[Observation, ...]
    choices: tuple[Choice, ...]


def offline_policy(view: View) -> Choice:
    if view.goal == GOALS[PRINCESS] and any(m.source == MANUSCRIPT for m in view.memory):
        return next((c for c in view.choices if c.action == "ask_registry"), view.choices[0])
    return view.choices[0]


class Investigation:
    def __init__(self):
        self.version = 0
        self.events: list[Event] = []
        self.memory = {actor: [] for actor in ROLES}
        self.intent = {actor: "等待相关线索" for actor in ROLES}
        self._disclosed = set()

    def _event(self, cause, kind, actor, audience, source, text):
        e = Event(len(self.events) + 1, cause, kind, actor, tuple(audience), source, text)
        self.events.append(e)
        return e

    def _observe(self, actor, event, kind):
        if actor not in event.audience:
            raise ValueError("收件人未获授权")
        self.memory[actor].append(Observation(event.seq, event.source, kind, event.text))

    def _choices(self, actor, event):
        options = [Choice("hold", actor, event.source)]
        if (actor == PRINCESS and event.kind == "show" and actor in event.audience
                and event.source == MANUSCRIPT):
            options.append(Choice("ask_registry", CENSOR, MANUSCRIPT))
        return tuple(options)

    def _react(self, actor, trigger, policy):
        choices = self._choices(actor, trigger)
        view = View(actor, GOALS[actor], tuple(self.memory[actor]), choices)
        try:
            proposal = policy(view)
        except Exception:
            proposal = None
        if not isinstance(proposal, Choice) or proposal not in choices:
            self._event(trigger.seq, "rejected", actor, (), trigger.source, "未选中合法候选，未执行")
            return
        decision = self._event(trigger.seq, "accepted", actor, (), proposal.source, proposal.action)
        if proposal.action == "ask_registry":
            self.intent[actor] = "等待核对登记"
            message = self._event(decision.seq, "private_question", actor, (actor, proposal.target),
                                  "message:" + str(decision.seq), "有人在查询秘录的登记。")
            self._observe(proposal.target, message, "heard_claim")
            self.intent[proposal.target] = "允许调查者追问登记来源"
        # No recursive dispatch from private messages. At most one decision per trigger.

    def apply(self, version: int, action: str, actor: str, source: str,
              policy: Callable[[View], Choice] = offline_policy):
        if version != self.version:
            raise ValueError("操作版本已过期")
        if actor not in ROLES:
            raise ValueError("案件中没有这个调查对象")
        if action == "show" and source == MANUSCRIPT:
            if (actor, source) in self._disclosed:
                raise ValueError("该人物已看过这份材料")
            self._disclosed.add((actor, source))
            event = self._event(None, "show", PLAYER, (PLAYER, actor), source, "你出示了秘录遗失记录。")
            self._observe(actor, event, "shown_record")
            self._react(actor, event, policy)
            reply = "我看过这份记录了，仅凭遗失登记无法确定是谁取走了原件。"
        elif action == "ask" and source == "registry":
            heard = next((m for m in self.memory[actor] if m.kind == "heard_claim"), None)
            reply = ("有人托我核对过这份登记。你可以再问我是谁提出的。" if heard
                     else "我还没有收到过关于这份登记的询问。")
            self._event(heard.cause if heard else None, "statement", actor, (actor, PLAYER),
                        heard.source if heard else "self:"+actor, reply)
        elif action == "ask" and source == "registry_origin":
            heard = next((m for m in self.memory[actor] if m.kind == "heard_claim"), None)
            if not heard or not any(e.kind=="statement" and e.actor==actor and e.source==heard.source for e in self.events):
                raise ValueError("尚无可追问的来源，请先询问登记")
            sender = self.events[heard.cause - 1].actor
            reply = f"据我亲历，是{sender}来问的。我只能说明她问过，不能据此指认取走秘录的人。"
            self._event(heard.cause, "statement", actor, (actor, PLAYER), heard.source, reply)
        else:
            raise ValueError("该操作或材料不属于本宗案件")
        self.version += 1
        return {"version": self.version, "reply": reply, "driver": "离线规则"}
