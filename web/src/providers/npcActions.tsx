import React, { createContext, useContext, useEffect, useRef } from 'react';
import { API_URL } from '../constants';
import { Actor, LLMMessage, useMysteryContext } from './mysteryContext';

type Ticket = { run: string; version: number };
type Move = { action: 'show' | 'ask'; actor: string; source: string };
type Dispatch = (actor: Actor, action: Move['action'], source: string, message: string) => Promise<void>;
const Context = createContext<Dispatch | null>(null);
export const useNpcActions = () => useContext(Context);

async function post(route: string, input: unknown, token?: string) {
  const response = await fetch((API_URL || 'http://localhost:10000') + '/npc/' + route, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    const failure = await response.json();
    throw new Error(typeof failure.detail === 'string' ? failure.detail : '调查行动未完成');
  }
  return response.json();
}

// This provider follows a mounted case. Switching people shares a run; reopening a case starts fresh.
export function NpcActions({ caseId, children }: React.PropsWithChildren<{caseId: string}>) {
  const { setActors } = useMysteryContext();
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const ticket = useRef<Promise<Ticket> | null>(null);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const dispatch: Dispatch = (actor, action, source, message) => {
    const append = (role: LLMMessage['role'], content: string) => {
      if (!mounted.current) return;
      setActors(all => {
        const current = all[actor.id];
        if (!mounted.current || !current || current.name !== actor.name) return all;
        return { ...all, [actor.id]: { ...current, messages: [...current.messages, { role, content }] } };
      });
    };
    append('user', message);
    const result = queue.current.then(async () => {
      if (!mounted.current) return;
      if (!ticket.current) ticket.current = post('runs', { case: caseId }).catch(error => {
        ticket.current = null;
        throw error;
      });
      const run = await ticket.current;
      const result = await post('act', { actor: actor.name, action, source, version: run.version }, run.run);
      run.version = result.version;
      append('assistant', '【离线行动】' + result.reply);
    }).catch(error => append('assistant', '【行动未完成】' + (error instanceof Error ? error.message : '连接失败')));
    queue.current = result;
    return result;
  };
  return <Context.Provider value={caseId === 'example_4' ? dispatch : null}>{children}</Context.Provider>;
}

export const tracksActor = (actor: Actor) => ['太平公主', '御史大夫', '张昌宗'].includes(actor.name);
export const tracksEvidence = (actor: Actor, id: string) => tracksActor(actor) && id === 'evidence_manuscript_missing';

export function registryQuestion(text: string): string | null {
  if (!/登记|秘录/.test(text)) return null;
  if (/谁.{0,8}(问|查)|谁.{0,6}(提出|来过)|来源是谁/.test(text)) return 'registry_origin';
  if (/查|问|情况|消息|线索/.test(text)) return 'registry';
  return null;
}
