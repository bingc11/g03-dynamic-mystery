"""Player-facing NPC routes. Internal events and role memories stay in the store."""
from contextlib import contextmanager

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from npc_dialogue import Dialogue, load_case, new_state
from npc_store import BusyRun, MissingRun, Receipt, digest, encode, store


router = APIRouter(prefix="/npc")


class Start(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case: str = Field(min_length=1, max_length=100)


class Say(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(min_length=1, max_length=128)
    actor: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=4000)
    evidence: str | None = Field(default=None, max_length=128)


class Resume(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    task_id: str = Field(min_length=1, max_length=128)


def get_case(case_id: str):
    case = load_case(case_id)
    if case is None:
        raise HTTPException(404, "本轮未配置此案")
    return case


def run_key(authorization: str = Header(default="")) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or len(token) != 40 or not token.isascii():
        raise HTTPException(404, "找不到调查会话")
    return digest(token)


@contextmanager
def claim_run(key):
    try:
        with store().claim(key) as run:
            yield run
    except MissingRun as exc:
        raise HTTPException(404, "找不到调查会话") from exc
    except BusyRun as exc:
        raise HTTPException(409, "这局调查正在处理另一条行动，请稍后重试", headers={"Retry-After": "1"}) from exc


def identical_request(receipt: Receipt, input_digest: str):
    if receipt.input_digest != input_digest:
        raise HTTPException(409, "请求标识已用于另一条对话")
    return receipt.result


@router.get("/cases/{case_id}")
def case_metadata(case_id: str):
    case = get_case(case_id)
    return {"actors": list(case["roles"]), "evidence": list(case["evidence"])}


@router.post("/runs", status_code=201)
def start(request: Start):
    case = get_case(request.case)
    token = store().create(request.case, new_state(case))
    return {"run": token, "version": 0}


@router.post("/dialogue")
def dialogue(request: Say, key: str = Depends(run_key)):
    db = store()
    input_digest = digest(encode([request.actor, request.text, request.evidence]))
    previous = db.receipt(key, request_id=request.request_id)
    if previous:
        return identical_request(previous, input_digest)
    with claim_run(key) as run:
        previous = db.receipt(key, request_id=request.request_id)
        if previous:
            return identical_request(previous, input_digest)
        case = get_case(run.case_id)
        if request.actor not in case["roles"]:
            raise HTTPException(404, "案件中没有这个调查对象")
        game = Dialogue(case, run.snapshot)
        result = game.submit(request.request_id, request.actor, request.text, request.evidence)
        run.save(Receipt(request.request_id, input_digest, result))
        return result


@router.get("/state")
def state(response: Response, key: str = Depends(run_key)):
    try:
        case_id, snapshot = store().read(key)
    except MissingRun as exc:
        raise HTTPException(404, "找不到调查会话") from exc
    response.headers["Cache-Control"] = "no-store"
    return Dialogue(get_case(case_id), snapshot).public_state()


@router.post("/resume")
def resume(request: Resume, key: str = Depends(run_key)):
    db = store()
    with claim_run(key) as run:
        receipt = db.receipt(key, task_id=request.task_id)
        if receipt is None:
            raise HTTPException(404, "这局调查中找不到该委托")
        if receipt.result["task"]["status"] != "accepted":
            return receipt.result
        game = Dialogue(get_case(run.case_id), run.snapshot)
        result = game.resume(request.task_id)
        run.save(Receipt(receipt.request_id, receipt.input_digest, result))
        return result
