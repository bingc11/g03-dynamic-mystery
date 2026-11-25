import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Button, Center, Stack, Text, TextInput } from '@mantine/core';
import { nanoid } from 'nanoid';
import { API_URL } from '../constants';
import { EvidenceInventory } from '../types/evidence';
import { Actor, useMysteryContext } from './mysteryContext';
import { SessionProvider } from './sessionContext';

type VerdictOptions = { suspects: string[]; motives: string[] };
type CaseActions = { actors: string[]; evidence: string[]; verdict?: VerdictOptions };
type Turn = {
  id: string; actor: string; text: string; reply: string; source?: string;
  source_name?: string; driver?: string; classification?: string;
};
type Task = { id: string; status: string; actor: string };
type RunState = { turns: Turn[]; tasks: Task[] };
type Outcome = { handled: boolean; turn?: Turn; task?: Task; driver?: string };
type Request = { request_id: string; actor: string; text: string; evidence?: string };
type Seat = { id: string; name: string };
export type InvestigationEvent = {
  id: string; actor: string; text: string; source?: string; classification?: string;
  cause?: string; time?: string | number; kind?: string; driver?: string; view?: string;
  source_name?: string; observer?: string;
};
type InvestigationRoom = {
  case_id: string; self: Seat; players: Seat[]; evidence: string[];
  evidence_details?: EvidenceInventory['details']; public: InvestigationEvent[]; solved: boolean;
};
type AssistLevel = 'summary' | 'nudge' | 'answer';
export type AssistResult = { text: string; driver?: string };

type DispatchResult = 'handled' | 'chat' | 'legacy';
type Actions = {
  managed: boolean;
  verdictOptions?: VerdictOptions;
  room: InvestigationRoom | null;
  inventory?: EvidenceInventory;
  dispatch: (actor: Actor, text: string, evidence?: string) => Promise<DispatchResult>;
  createInvite: () => Promise<string>;
  share: (turnId: string) => Promise<void>;
  replay: () => Promise<InvestigationEvent[]>;
  assist: (level: AssistLevel, query?: string) => Promise<AssistResult>;
  verdict: (suspect: string, motive: string) => Promise<{ correct: boolean; message: string }>;
  finish: () => void;
};
const Context = createContext<Actions | null>(null);
export const useNpcActions = () => useContext(Context);

export function decisionLabel(driver?: string) {
  if (driver === 'llm' || driver === 'deepseek') return '模型决策';
  if (driver === 'mock') return '模拟决策';
  if (driver === 'fallback') return '规则降级';
  if (driver === 'rules') return '规则裁定';
}

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
  caseId, playthrough, invite, children,
}: React.PropsWithChildren<{ caseId: string; playthrough: string; invite?: string }>) {
  const { setActors } = useMysteryContext();
  const [storageKey] = useState(() => {
    // Each direct invite gets a separate browser-history slot, even on a
    // shared browser whose initial React Router location key is "default".
    const historyState = window.history.state;
    let slot = historyState?.npcRoomSlot as string | undefined;
    if (invite && !slot) {
      slot = nanoid();
      window.history.replaceState({ ...historyState, npcRoomSlot: slot }, '');
    }
    return 'npc-run:' + caseId + ':' + (slot || playthrough);
  });
  const pendingKey = storageKey + ':pending';
  const token = useRef(sessionStorage.getItem(storageKey));
  const pending = useRef<Request[]>(readPending(pendingKey));
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const mounted = useRef(false);
  const finished = useRef(false);
  const restored = useRef(false);
  const roomRead = useRef(0);
  const [caseActions, setCaseActions] = useState<CaseActions | null>();
  const [setupError, setSetupError] = useState('');
  const [room, setRoom] = useState<InvestigationRoom | null>(null);
  const [seatName, setSeatName] = useState('');
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState('');
  const [joined, setJoined] = useState(Boolean(token.current));
  const [notebook] = useState(() => {
    const key = storageKey + ':notebook';
    const id = sessionStorage.getItem(key) || 'investigation-' + nanoid();
    sessionStorage.setItem(key, id);
    return id;
  });
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

  const loadCase = useCallback(async () => {
    setSetupError('');
    try {
      const available = await request<CaseActions>('cases/' + encodeURIComponent(caseId));
      if (mounted.current) setCaseActions(available);
    } catch (error) {
      if (!mounted.current) return;
      if (error instanceof RequestError && error.status === 404) setCaseActions(null);
      else setSetupError(error instanceof Error ? error.message : '暂时无法读取调查配置');
    }
  }, [caseId]);

  const loadRoom = useCallback(async (run: string) => {
    const read = ++roomRead.current;
    const result = await request<InvestigationRoom>('room', undefined, run);
    if (mounted.current && token.current === run && read === roomRead.current) {
      setRoom(previous => JSON.stringify(previous) === JSON.stringify(result) ? previous : result);
    }
  }, []);

  const saveToken = useCallback((run: string) => {
    token.current = run;
    sessionStorage.setItem(storageKey, run);
    setJoined(true);
  }, [storageKey]);

  const ensureRun = useCallback(async () => {
    if (token.current) return token.current;
    if (invite) throw new Error('请先加入调查');
    const { run } = await request<{ run: string }>('runs', { case: caseId });
    saveToken(run);
    restored.current = true;
    return run;
  }, [caseId, invite, saveToken]);

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
          const reply = {
            role: 'assistant' as const, content: turn.reply, npcTurnId: turn.id,
            npcDriver: turn.driver, npcSource: turn.source_name ?? turn.source, npcClassification: turn.classification,
          };
          const assistant = messages.findIndex(message => message.npcTurnId === turn.id && message.role === 'assistant');
          if (assistant >= 0) {
            messages[assistant] = reply;
          } else {
            messages.push(
              { role: 'user', content: turn.text, npcTurnId: turn.id },
              reply,
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
    if (outcome.turn) remember([{ ...outcome.turn, driver: outcome.turn.driver ?? outcome.driver }]);
    void loadRoom(run).catch(() => undefined);
  }, [loadRoom, remember]);

  const submit = useCallback(async (run: string, move: Request) => {
    const outcome = await retryWhileProcessing(() => request<Outcome>('dialogue', move, run));
    remember(outcome.turn ? [{ ...outcome.turn, driver: outcome.turn.driver ?? outcome.driver }] : [], 'retry:' + move.request_id);
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
    void loadCase();
    void enqueue(restore).catch(() => undefined);
    return () => { mounted.current = false; };
  }, [enqueue, loadCase, restore]);

  useEffect(() => {
    if (!joined || !caseActions) return;
    const refresh = () => {
      if (token.current && !document.hidden) void loadRoom(token.current).catch(() => undefined);
    };
    refresh();
    const interval = window.setInterval(refresh, 4000);
    window.addEventListener('focus', refresh);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener('focus', refresh);
    };
  }, [caseActions, joined, loadRoom]);

  const join = async () => {
    if (!invite || !seatName.trim() || joining) return;
    setJoining(true);
    setJoinError('');
    try {
      const pendingSeatKey = storageKey + ':joining';
      const seatToken = sessionStorage.getItem(pendingSeatKey) || nanoid(40);
      sessionStorage.setItem(pendingSeatKey, seatToken);
      const result = await request<{ run: string; case_id: string }>('runs/join', {
        invite, name: seatName.trim(), case: caseId, seat_token: seatToken,
      });
      if (result.case_id !== caseId) throw new Error('邀请与当前剧本不匹配');
      saveToken(result.run);
      sessionStorage.removeItem(pendingSeatKey);
      const url = new URL(window.location.href);
      url.searchParams.delete('invite');
      window.history.replaceState(window.history.state, '', url);
    } catch (error) {
      setJoinError(error instanceof Error ? error.message : '暂时无法加入调查');
    } finally {
      setJoining(false);
    }
  };

  const perform = <T,>(route: string, body?: unknown, refresh = false) =>
    enqueue(async () => {
      const run = await ensureRun();
      const result = await retryWhileProcessing(() => request<T>(route, body, run));
      if (refresh) void loadRoom(run).catch(() => undefined);
      return result;
    });

  const dispatch: Actions['dispatch'] = (actor, text, evidence) => enqueue(async () => {
    if (!active()) return 'handled';
    let turn: Turn | undefined;
    let sent: Request | undefined;
    try {
      if (!active()) return 'handled';
      if (!caseActions) return 'legacy';
      if (!caseActions.actors.includes(actor.name)) return 'chat';
      if (evidence && !caseActions.evidence.includes(evidence)) return 'chat';
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
      const run = await ensureRun();
      const result = await submit(run, move);
      turn = result.turn;
      if (result.task?.status === 'accepted') await resume(run, result.task);
      else if (evidence) void loadRoom(run).catch(() => undefined);
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

  const inventory = useMemo<EvidenceInventory | undefined>(() =>
    room && caseActions
      ? { held: room.evidence, registered: caseActions.evidence, details: room.evidence_details || [] }
      : undefined,
  [caseActions, room]);

  const actions: Actions = {
    managed: Boolean(caseActions), verdictOptions: caseActions?.verdict, room, inventory, dispatch,
    createInvite: async () => {
      const result = await perform<{ invite: string }>('invite', {}, true);
      const url = new URL('/play/' + encodeURIComponent(caseId), window.location.origin);
      url.searchParams.set('invite', result.invite);
      return url.href;
    },
    share: async (turnId) => { await perform('share', { turn_id: turnId }, true); },
    replay: async () => (await perform<{ events: InvestigationEvent[] }>('replay')).events,
    assist: (level, query) => perform('assist', { level, query }),
    verdict: (suspect, motive) => perform('verdict', { suspect, motive }, true),
    finish: () => { finished.current = true; },
  };

  const waiting = caseActions === undefined;
  if (waiting || (invite && !joined)) {
    return (
      <Center mih="60vh">
        <Stack w={360} p="md">
          {waiting ? (
            <>
              <Text role={setupError ? 'alert' : 'status'}>{setupError || '正在读取调查配置…'}</Text>
              {setupError && <Button onClick={() => void loadCase()}>重试</Button>}
            </>
          ) : (
            <form onSubmit={event => { event.preventDefault(); void join(); }}>
              <Stack>
                <Text fw={700}>加入同一案件</Text>
                <TextInput label="姓名" value={seatName} onChange={event => setSeatName(event.currentTarget.value)} maxLength={32} required />
                {joinError && <Text role="alert" c="red">{joinError}</Text>}
                <Button type="submit" loading={joining} disabled={!seatName.trim()}>加入调查</Button>
              </Stack>
            </form>
          )}
        </Stack>
      </Center>
    );
  }

  return (
    <Context.Provider value={actions}>
      {caseActions ? <SessionProvider scope={notebook}>{children}</SessionProvider> : children}
    </Context.Provider>
  );
}
