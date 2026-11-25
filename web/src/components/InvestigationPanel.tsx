import React, { useState } from 'react';
import { Badge, Button, Group, Select, Stack, Text, TextInput } from '@mantine/core';
import { AssistResult, decisionLabel, InvestigationEvent, useNpcActions } from '../providers/npcActions';

const eventNames: Record<string, string> = {
  show: '出示证物', evidence_acquired: '获得证物', delegation: '发起委托',
  accepted: '接受委托', declined: '委托未受理',
  report: '委托回报', statement: '角色陈述', conversation: '对话',
  conversation_reply: '对话回报', player_note: '玩家笔记', decision: '角色决定', cancelled: '取消委托',
  shared: '公开线索', hint: '调查提示', verdict: '结案',
};

function eventTime(value?: string | number) {
  if (!value) return '';
  const date = new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString();
}

export default function InvestigationPanel() {
  const actions = useNpcActions();
  const [invite, setInvite] = useState('');
  const [copied, setCopied] = useState(false);
  const [events, setEvents] = useState<InvestigationEvent[] | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const [role, setRole] = useState<string | null>(null);
  const [through, setThrough] = useState<string | undefined>();
  const [hint, setHint] = useState<AssistResult | null>(null);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState('');
  if (!actions?.managed) return null;
  const { room } = actions;
  const names = new Map(room?.players.map(player => [player.id, player.name]));
  const indices = new Map(events?.map((event, index) => [event.id, index + 1]));

  async function run(label: string, work: () => Promise<void>) {
    setBusy(label);
    setError('');
    try {
      await work();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : '暂时无法完成操作');
    } finally {
      setBusy(null);
    }
  }

  async function replay(selected: string | null, endpoint?: string) {
    if (!actions) return;
    const result = await actions.replay(selected ?? undefined, endpoint);
    setRole(selected);
    setThrough(endpoint);
    setEvents(result.events);
    setRoles(result.roles);
  }

  return (
    <Stack gap="md" p="xs" c="gray.1" aria-label="调查记录">
      <Stack gap="xs">
        <Text size="sm" fw={700}>同局调查</Text>
        {room && (
          <>
            <Text size="xs">当前席位 {room.self.name}</Text>
            <Group gap={4}>
              {room.players.map(player => <Badge key={player.id} color="cyan" variant="light">{player.name}</Badge>)}
            </Group>
          </>
        )}
        {(!room || room.self.id === '$player') && (
          <Button
            size="compact-sm" variant="light" color="cyan" w="fit-content"
            disabled={busy !== null} loading={busy === 'invite'}
            onClick={() => void run('invite', async () => { setInvite(await actions.createInvite()); setCopied(false); })}
          >
            邀请玩家
          </Button>
        )}
        {invite && (
          <Group gap="xs">
            <TextInput label="邀请链接" aria-label="邀请链接" value={invite} readOnly onFocus={event => event.currentTarget.select()} style={{ flex: 1 }} />
            {navigator.clipboard && (
              <Button
                mt="lg" size="compact-sm" variant="light"
                onClick={() => void run('copy', async () => { await navigator.clipboard.writeText(invite); setCopied(true); })}
              >
                {copied ? '已复制' : '复制'}
              </Button>
            )}
          </Group>
        )}
      </Stack>
      <Stack gap="xs">
        <Text size="sm" fw={700}>公开线索</Text>
        {room?.public.length ? room.public.map(event => (
          <Stack gap={2} key={event.id} p="xs" style={{ borderLeft: '2px solid #00C2FF', background: 'rgba(0, 194, 255, 0.06)' }}>
            <Text size="xs" c="cyan.3">{names.get(event.actor) ?? event.actor}{event.source_name ? ` · ${event.source_name}` : ''}</Text>
            <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{event.text}</Text>
          </Stack>
        )) : <Text size="xs" c="gray.4">目前没有公开线索。可在对话中公开一条回报。</Text>}
      </Stack>
      <Stack gap="xs">
        <Text size="sm" fw={700}>调查提示</Text>
        <TextInput
          aria-label="想核对的问题"
          placeholder="想核对的问题（选填）"
          value={query}
          onChange={event => setQuery(event.currentTarget.value)}
          maxLength={240}
        />
        <Group gap="xs">
          <Button size="compact-sm" variant="light" disabled={busy !== null} loading={busy === 'summary'}
            onClick={() => void run('summary', async () => setHint(await actions.assist('summary', query.trim() || undefined)))}>
            总结线索
          </Button>
          <Button size="compact-sm" variant="light" disabled={busy !== null} loading={busy === 'nudge'}
            onClick={() => void run('nudge', async () => setHint(await actions.assist('nudge', query.trim() || undefined)))}>
            下一步提示
          </Button>
          <Button size="compact-sm" variant="light" disabled={busy !== null || !query.trim()} loading={busy === 'plan'}
            onClick={() => void run('plan', async () => setHint(await actions.assist('plan', query.trim())))}>
            拆解调查目标
          </Button>
          {room?.solved && <Button size="compact-sm" variant="light" color="teal" disabled={busy !== null} loading={busy === 'answer'}
            onClick={() => void run('answer', async () => setHint(await actions.assist('answer')))}>
            查看结案解释
          </Button>}
        </Group>
        {hint && <Stack gap={2} aria-live="polite">
          {decisionLabel(hint.driver) && <Text size="xs" c="cyan.3">{decisionLabel(hint.driver)}</Text>}
          <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{hint.text}</Text>
          {hint.steps?.map((step, index) => <Stack key={index} gap={3}>
            <Text size="sm">{index + 1}. {step.actor} · {step.text}</Text>
            {step.prepare.length > 0 && <Text size="xs" c="gray.4">先出示 {step.prepare.join('、')}</Text>}
            <Button size="compact-xs" variant="light" w="fit-content" onClick={() => actions.setDraft(step)}>
              填入{step.actor}的对话框
            </Button>
          </Stack>)}
          {actions.draft && <Text size="xs">切换到{actions.draft.actor}，编辑后发送。</Text>}
        </Stack>}
      </Stack>
      <Stack gap="xs">
        <Group justify="space-between">
          <Text size="sm" fw={700}>调查复盘</Text>
          <Button size="compact-sm" variant="subtle" color="cyan" disabled={busy !== null} loading={busy === 'replay'}
            onClick={() => void run('replay', () => replay(role))}>
            更新复盘
          </Button>
        </Group>
        {roles.length > 0 && <Select label="角色视角" placeholder="本席位可见的全部事件" clearable
          data={roles} value={role} disabled={busy !== null}
          onChange={value => void run('replay', () => replay(value, through))} />}
        {through && <Text size="xs" c="gray.4">正在查看截至所选事件的记录。</Text>}
        {events?.length === 0 && <Text size="xs" c="gray.4">目前没有可回看的调查节点。</Text>}
        {events?.map((event, index) => (
          <Stack key={event.id} gap={2} p="xs" style={{ borderLeft: '2px solid #4ECCA3', background: 'rgba(78, 204, 163, 0.06)' }}>
            <Text size="xs" c="teal.3">
              {index + 1}. {names.get(event.actor) ?? event.actor} · {eventNames[event.kind || ''] ?? '调查节点'}
              {event.time && eventTime(event.time) ? ` · ${eventTime(event.time)}` : ''}
            </Text>
            <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{event.text}</Text>
            <Group gap={4}>
              {['fact', 'claim'].includes(event.classification || '') && <Badge color={event.classification === 'fact' ? 'teal' : 'yellow'} variant="light" size="xs">
                {event.classification === 'fact' ? '已核实材料' : '角色主张'}
              </Badge>}
              {event.classification === 'note' && <Badge color="gray" variant="light" size="xs">玩家推测</Badge>}
              {event.view && <Text size="xs" c="gray.4">
                {event.view === 'prior_public' ? '加入前已公开'
                  : event.view === 'public' ? '当时同局公开'
                    : event.view === 'npc_statement' ? '当时由角色告知' : '当时本席位可见'}
              </Text>}
              {event.observer && <Text size="xs" c="gray.4">当时获知 {event.observer}</Text>}
              {event.recipient && event.recipient !== event.observer && <Text size="xs" c="gray.4">接收者 {event.recipient}</Text>}
              {event.source_name && <Text size="xs" c="gray.4">来源 {event.source_name}</Text>}
              {event.cause && indices.has(event.cause) && <Text size="xs" c="gray.4">依据第 {indices.get(event.cause)} 步</Text>}
              {decisionLabel(event.driver) && <Text size="xs" c="gray.4">{decisionLabel(event.driver)}</Text>}
              <Button size="compact-xs" variant="subtle" disabled={busy !== null} onClick={() => void run('replay', () => replay(role, event.id))}>
                查看至此
              </Button>
            </Group>
          </Stack>
        ))}
      </Stack>
      {error && <Text role="alert" c="red.3" size="sm">{error}</Text>}
    </Stack>
  );
}
