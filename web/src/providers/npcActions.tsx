import React, { createContext, useCallback, useContext, useEffect, useRef } from 'react';
import { nanoid } from 'nanoid';
import { API_URL } from '../constants';
import { Actor, useMysteryContext } from './mysteryContext';

type CaseActions = { actors: string[]; evidence: string[] };
type Turn = { id: string; actor: string; text: string; reply: string };
type Task = { id: string; status: string; actor: string };
type RunState = { turns: Turn[]; tasks: Task[] };
type Outcome = { handled: boolean; turn?: Turn; task?: Task };
type Request = { request_id: string; actor: string; text: string; evidence?: string };

type DispatchResult = 'handled' | 'chat' | 'legacy';
type Actions = {
  dispatch: (actor: Actor, text: string, evidence?: string) => Promise<DispatchResult>;
  finish: () => void;
};
const Context = createContext<Actions | null>(null);
export const useNpcActions = () => useContext(Context);

class RequestError extends Error {
  constructor(readonly status: number, message: string, readonly processing: boolean) {
    super(message);
  }
}

async function request<T>(route: string, input?: unknown, token?: string): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 25_000);
  try {
    const response = await fetch(API_URL + '/npc/' + route, {
      method: input === undefined ? 'GET' : 'POST',
      headers: {
        ...(input === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { Authorization: 'Bearer ' + token } : {}),
      },
      body: input === undefined ? undefined : JSON.stringify(input),
      signal: controller.signal,
    });
    const body = await response.json();
    if (!response.ok) {
      throw new RequestError(
        response.status,
        typeof body.detail === 'string' ? body.detail : '调查行动未完成',
        response.status === 409 && response.headers.has('Retry-After'),
      );
    }
    return body;
  } finally {
    clearTimeout(timer);
  }
}

const retryable = (error: unknown) => !(error instanceof RequestError) || error.processing || error.status >= 500;

async function retryWhileProcessing<T>(work: () => Promise<T>) {
  const deadline = Date.now() + 22_000;
  while (true) {
    try {
      return await work();
    } catch (error) {
      if (!(error instanceof RequestError && error.processing) || Date.now() >= deadline) throw error;
      await new Promise(resolve => setTimeout(resolve, 1_000));
    }
  }
}

function readPending(key: string): Request[] {
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) || '[]');
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

export function NpcActions({
  caseId, playthrough, children,
}: React.PropsWithChildren<{ caseId: string; playthrough: string }>) {
  const { setActors } = useMysteryContext();
  const storageKey = 'npc-run:' + caseId + ':' + playthrough;
  const pendingKey = storageKey + ':pending';
  const token = useRef(sessionStorage.getItem(storageKey));
  const pending = useRef<Request[]>(readPending(pendingKey));
  const capabilities = useRef<Promise<CaseActions | null> | null>(null);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const mounted = useRef(false);
  const finished = useRef(false);
  const restored = useRef(false);
  const active = useCallback(() => mounted.current && !finished.current, []);

  const enqueue = useCallback(<T,>(work: () => Promise<T>) => {
    const result = queue.current.then(work);
    queue.current = result.catch(() => undefined);
    return result;
  }, []);

  const savePending = useCallback((requests: Request[]) => {
    pending.current = requests;
    sessionStorage.setItem(pendingKey, JSON.stringify(requests));
  }, [pendingKey]);

  const remember = useCallback((turns: Turn[], removeAttempt?: string) => {
    if (!active()) return;
    setActors(all => {
      if (!active()) return all;
      const next = { ...all };
      for (const actor of Object.values(all)) {
        const incoming = turns.filter(turn => turn.actor === actor.name);
        const hasAttempt = !!removeAttempt && actor.messages.some(message => message.npcTurnId === removeAttempt);
        if (!incoming.length && !hasAttempt) continue;
        const messages = actor.messages.filter(message => !removeAttempt || message.npcTurnId !== removeAttempt);
        for (const turn of incoming) {
          const assistant = messages.findIndex(message => message.npcTurnId === turn.id && message.role === 'assistant');
          if (assistant >= 0) {
            messages[assistant] = { role: 'assistant', content: turn.reply, npcTurnId: turn.id };
          } else {
            messages.push(
              { role: 'user', content: turn.text, npcTurnId: turn.id },
              { role: 'assistant', content: turn.reply, npcTurnId: turn.id },
            );
          }
        }
        next[actor.id] = { ...actor, messages };
      }
      return next;
    });
  }, [active, setActors]);

  const resume = useCallback(async (run: string, task: Task) => {
    const outcome = await retryWhileProcessing(() => request<Outcome>('resume', { task_id: task.id }, run));
    if (outcome.turn) remember([outcome.turn]);
  }, [remember]);

  const submit = useCallback(async (run: string, move: Request) => {
    const outcome = await retryWhileProcessing(() => request<Outcome>('dialogue', move, run));
    remember(outcome.turn ? [outcome.turn] : [], 'retry:' + move.request_id);
    return outcome;
  }, [remember]);

  const clearPending = useCallback((move: Request) => {
    savePending(pending.current.filter(previous => previous.request_id !== move.request_id));
  }, [savePending]);

  const restore = useCallback(async () => {
    const run = token.current;
    if (!run || !active() || restored.current) return;
    const state = await request<RunState>('state', undefined, run);
    remember(state.turns);
    for (const task of state.tasks) {
      if (!active()) return;
      if (task.status === 'accepted') await resume(run, task);
    }
    // The original request may have committed after the state read. Reusing
    // its ID lets the server recover either the receipt or the pending task.
    for (const move of pending.current) {
      if (!active()) return;
      try {
        const outcome = await submit(run, move);
        if (outcome.task?.status === 'accepted') await resume(run, outcome.task);
        clearPending(move);
      } catch (error) {
        if (retryable(error)) throw error;
        clearPending(move);
      }
    }
    restored.current = true;
  }, [active, clearPending, remember, resume, submit]);

  useEffect(() => {
    mounted.current = true;
    // If the API is still restarting, the next action retries restoration.
    void enqueue(restore).catch(() => undefined);
    return () => { mounted.current = false; };
  }, [enqueue, restore]);

  const dispatch: Actions['dispatch'] = (actor, text, evidence) => enqueue(async () => {
    if (!active()) return 'handled';
    let turn: Turn | undefined;
    let sent: Request | undefined;
    try {
      if (!capabilities.current) {
        capabilities.current = request<CaseActions>('cases/' + encodeURIComponent(caseId)).catch(error => {
          if (error instanceof RequestError && error.status === 404) return null;
          capabilities.current = null;
          throw error;
        });
      }
      const available = await capabilities.current;
      if (!active()) return 'handled';
      if (!available?.actors.includes(actor.name)) return 'legacy';
      if (evidence && !available.evidence.includes(evidence)) return 'chat';
      await restore();
      if (!active()) return 'handled';
      sent = pending.current.find(previous =>
        previous.actor === actor.name && previous.text === text && previous.evidence === evidence
      );
      if (!sent) {
        sent = { request_id: nanoid(), actor: actor.name, text, evidence };
        savePending([...pending.current, sent]);
      }
      const move = sent;
      if (!token.current) {
        token.current = (await request<{ run: string }>('runs', { case: caseId })).run;
        sessionStorage.setItem(storageKey, token.current);
        restored.current = true;
      }
      const run = token.current;
      const result = await submit(run, move);
      turn = result.turn;
      if (result.task?.status === 'accepted') await resume(run, result.task);
      clearPending(move);
      if (active() && !result.handled) return 'chat';
    } catch (error) {
      const canRetry = retryable(error);
      const reason = error instanceof RequestError ? error.message : '连接中断或等待超时';
      const followUp = canRetry ? '。请原样重新发送以取回回复。'
        : error instanceof RequestError && error.status === 404 ? '。请从剧本库开始新调查。' : '。';
      const failure = turn
        ? { ...turn, reply: turn.reply + '\n\n委托回报暂不可用：' + reason + followUp }
        : { id: 'retry:' + (sent?.request_id ?? nanoid()), actor: actor.name, text, reply: '调查对话暂不可用：' + reason + followUp };
      remember([failure]);
      if (sent && !canRetry) {
        clearPending(sent);
      }
    }
    return 'handled';
  });

  return <Context.Provider value={{ dispatch, finish: () => { finished.current = true; } }}>{children}</Context.Provider>;
}
