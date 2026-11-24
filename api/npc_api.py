"""Local single-process sessions. A random capability identifies a single playthrough."""
import secrets
import threading
import time
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from npc_actions import CASE, Investigation

router = APIRouter(prefix="/npc")
lock = threading.Lock()
runs = {}
TTL = 12 * 3600


class Start(BaseModel):
    case: str


class Move(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: int = Field(ge=0)
    action: str = Field(max_length=12)
    actor: str = Field(max_length=40)
    source: str = Field(max_length=80)


@router.post("/runs", status_code=201)
def start(request: Start):
    if request.case != CASE:
        raise HTTPException(404, "本轮未配置此案")
    with lock:
        now = time.monotonic()
        for key in [key for key, (_, used) in runs.items() if now-used >= TTL]:
            del runs[key]
        if len(runs) >= 256:
            raise HTTPException(503, "本机调查会话已满")
        key = secrets.token_urlsafe(30)
        runs[key] = (Investigation(), now)
        return {"run": key, "version": 0}


@router.post("/act")
def act(request: Move, authorization: str = Header(default="")):
    key = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
    with lock:
        now = time.monotonic()
        entry = runs.get(key)
        if not entry or now-entry[1] >= TTL:
            raise HTTPException(404, "调查会话已失效")
        game = entry[0]
        try:
            result = game.apply(request.version, request.action, request.actor, request.source)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        runs[key] = (game, now)
        return result
