"""Player-facing NPC routes. Internal events and role memories stay in the store."""
from contextlib import contextmanager
from copy import deepcopy
import os
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from npc_dialogue import Dialogue, load_case, new_state
from npc_decisions import ModelRequired
from npc_store import (
    HOST_PLAYER, BusyRun, FullRun, MissingRun, Receipt, Seat, SeatInUse, digest, encode, scoped_request_id, store,
)


router = APIRouter(prefix="/npc")


class PlayerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Start(PlayerRequest):
    case: str = Field(min_length=1, max_length=100)


class Join(PlayerRequest):
    invite: str = Field(min_length=40, max_length=40)
    name: str = Field(min_length=1, max_length=24)
    case: str | None = Field(default=None, min_length=1, max_length=100)
    seat_token: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{40}$")


class Say(PlayerRequest):
    request_id: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=4000)
    evidence: str | None = Field(default=None, max_length=128)
    note: bool = False


class Resume(PlayerRequest):
    task_id: str = Field(min_length=1, max_length=128)


class Share(PlayerRequest):
    turn_id: str = Field(min_length=1, max_length=256)


class Assist(PlayerRequest):
    level: Literal["summary", "nudge", "answer", "plan"]
    query: str = Field(default="", max_length=1000)


class Verdict(PlayerRequest):
    suspect: str = Field(min_length=1, max_length=100)
    motive: str = Field(min_length=1, max_length=256)


def get_case(case_id: str):
    case = load_case(case_id)
    if case is None:
        raise HTTPException(404, "本轮未配置此案")
    return case


def seat_access(authorization: str = Header(default="")) -> Seat:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or len(token) != 40 or not token.isascii():
        raise HTTPException(404, "找不到调查会话")
    try:
        return store().seat(digest(token))
    except MissingRun as exc:
        raise HTTPException(404, "找不到调查会话") from exc


@contextmanager
def claim_run(key):
    try:
        with store().claim(key) as run:
            yield run
    except MissingRun as exc:
        raise HTTPException(404, "找不到调查会话") from exc
    except BusyRun as exc:
        raise HTTPException(409, "这局调查正在处理另一条行动，请稍后重试", headers={"Retry-After": "1"}) from exc
    except FullRun as exc:
        raise HTTPException(409, "这局调查的玩家席位已满") from exc
    except SeatInUse as exc:
        raise HTTPException(409, "该席位凭据已被使用") from exc


@contextmanager
def player_operation():
    try:
        yield
    except KeyError as exc:
        raise HTTPException(404, "当前席位找不到这条调查记录") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@contextmanager
def model_operation(run):
    original = deepcopy(run.snapshot) if os.getenv("NPC_DECISION_MODE", "auto").lower() == "llm-required" else None
    try:
        yield
    except ModelRequired as exc:
        if original is not None:
            # Keep the model budget and diagnostics, roll back all gameplay changes and receipts.
            original["model"] = run.snapshot.get("model", {})
            run.snapshot.clear()
            run.snapshot.update(original)
            run.save()
        raise HTTPException(503, {"message": str(exc), "model_error": exc.status}) from exc


def read_game(response: Response, seat: Seat):
    try:
        case_id, snapshot = store().read(seat.run_hash)
    except MissingRun as exc:
        raise HTTPException(404, "找不到调查会话") from exc
    response.headers["Cache-Control"] = "no-store"
    return case_id, Dialogue(get_case(case_id), snapshot, player=seat.player)


def identical_request(receipt: Receipt, input_digest: str):
    if receipt.input_digest != input_digest:
        raise HTTPException(409, "请求标识已用于另一条对话")
    return receipt.result


@router.get("/cases/{case_id}")
def case_metadata(case_id: str):
    case = get_case(case_id)
    metadata = {"actors": list(case["roles"]),
                "evidence": [key for key, item in case["evidence"].items() if item.get("initial", True)]}
    if "title" in case:
        metadata["title"] = case["title"]
    if "verdict" in case:
        metadata["verdict"] = {name: case["verdict"][name] for name in ("suspects", "motives")}
    return metadata


@router.post("/runs", status_code=201)
def start(request: Start, response: Response):
    case = get_case(request.case)
    token = store().create(request.case, new_state(case))
    response.headers["Cache-Control"] = "no-store"
    return {"run": token, "version": 0}


@router.post("/invite")
def invite(response: Response, seat: Seat = Depends(seat_access)):
    if seat.player != HOST_PLAYER:
        raise HTTPException(403, "只有发起调查的玩家可以邀请其他人")
    response.headers["Cache-Control"] = "no-store"
    return {"invite": store().invite(seat.run_hash)}


@router.post("/runs/join", status_code=201)
def join(request: Join, response: Response):
    name = request.name.strip()
    if not name or not name.isprintable():
        raise HTTPException(400, "请输入玩家姓名")
    invite_hash = digest(request.invite)
    db = store()
    try:
        key = db.invitation_run(invite_hash)
    except MissingRun as exc:
        raise HTTPException(404, "邀请已失效") from exc
    with claim_run(key) as run, player_operation():
        if request.case is not None and request.case != run.case_id:
            raise HTTPException(404, "邀请和当前案件不匹配")
        response.headers["Cache-Control"] = "no-store"
        if request.seat_token:
            try:
                existing = db.seat(digest(request.seat_token))
            except MissingRun:
                existing = None
            if existing:
                if existing.run_hash != key or existing.player == HOST_PLAYER:
                    raise SeatInUse
                return {"run": request.seat_token, "version": 0, "case_id": run.case_id}
        player = f"{HOST_PLAYER}:{uuid4().hex}"
        game = Dialogue(get_case(run.case_id), run.snapshot, player=HOST_PLAYER)
        game.register_player(player, name)
        token = run.join(invite_hash, player, request.seat_token)
        return {"run": token, "version": 0, "case_id": run.case_id}


@router.post("/dialogue")
def dialogue(request: Say, seat: Seat = Depends(seat_access)):
    db = store()
    fields = [request.actor, request.text, request.evidence]
    if request.note:
        if request.evidence:
            raise HTTPException(400, "笔记与出示证物请分开发送")
        fields.append(True)
    input_digest = digest(encode(fields))
    previous = db.receipt(seat.run_hash, request_id=request.request_id, player=seat.player)
    if previous:
        return identical_request(previous, input_digest)
    with claim_run(seat.run_hash) as run, player_operation():
        previous = db.receipt(seat.run_hash, request_id=request.request_id, player=seat.player)
        if previous:
            return identical_request(previous, input_digest)
        case = get_case(run.case_id)
        if request.actor not in case["roles"]:
            raise HTTPException(404, "案件中没有这个调查对象")
        game = Dialogue(case, run.snapshot, player=seat.player)
        request_key = scoped_request_id(seat.player, request.request_id)
        with model_operation(run):
            result = game.submit(request_key, request.actor, request.text, request.evidence, note=request.note)
        run.save(Receipt(request_key, input_digest, result, seat.player))
        return result


@router.get("/state")
def state(response: Response, seat: Seat = Depends(seat_access)):
    _, game = read_game(response, seat)
    return game.public_state()


@router.post("/resume")
def resume(request: Resume, seat: Seat = Depends(seat_access)):
    db = store()
    with claim_run(seat.run_hash) as run, player_operation():
        receipt = db.receipt(seat.run_hash, task_id=request.task_id, player=seat.player)
        if receipt is None:
            raise HTTPException(404, "当前席位找不到该委托")
        if receipt.result["task"]["status"] != "accepted":
            return receipt.result
        game = Dialogue(get_case(run.case_id), run.snapshot, player=seat.player)
        with model_operation(run):
            result = game.resume(request.task_id)
        run.save(Receipt(receipt.request_id, receipt.input_digest, result, seat.player))
        return result


@router.get("/room")
def room(response: Response, seat: Seat = Depends(seat_access)):
    case_id, game = read_game(response, seat)
    return {"case_id": case_id, **game.room()}


@router.post("/share")
def share(request: Share, seat: Seat = Depends(seat_access)):
    with claim_run(seat.run_hash) as run, player_operation():
        game = Dialogue(get_case(run.case_id), run.snapshot, player=seat.player)
        result = game.share(request.turn_id)
        run.save()
        return result


@router.get("/replay")
def replay(response: Response, seat: Seat = Depends(seat_access), role: str | None = None, through: str | None = None):
    _, game = read_game(response, seat)
    with player_operation():
        return game.replay(role, through)


@router.post("/assist")
def assist(request: Assist, seat: Seat = Depends(seat_access)):
    with claim_run(seat.run_hash) as run, player_operation():
        game = Dialogue(get_case(run.case_id), run.snapshot, player=seat.player)
        with model_operation(run):
            result = game.assist(request.level, request.query)
        run.save()
        return result


@router.post("/verdict")
def verdict(request: Verdict, seat: Seat = Depends(seat_access)):
    with claim_run(seat.run_hash) as run, player_operation():
        game = Dialogue(get_case(run.case_id), run.snapshot, player=seat.player)
        result = game.verdict(request.suspect, request.motive)
        run.save()
        return result
