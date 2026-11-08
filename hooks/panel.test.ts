import { expect, test } from 'claude-code/testing'

import { applyResult, bandView, dismissOnPrompt, parseToolResult, reshowBand, stepLabel, stepsView, toPanel } from './panel'
import type { Status } from './panel'

const base: Status = { id: 's1', state: 'working', steps: [], summary: null, cost_cents: 0, cursor: 0 }

test('steps accumulate across polls and cost shows in dollars', () => {
  const first = toPanel(undefined, { ...base, steps: [{ seq: 2, tool: 'call_seqera_api' }], cursor: 2 })
  const done = toPanel(first, { ...base, state: 'done', summary: 'S12 ran out of memory.', cost_cents: 37, cursor: 9 })
  expect(done.steps.map(s => s.label)).toEqual(['Call seqera api'])
  expect(done.cost).toBe('$0.37')
  expect(done.summary).toBe('S12 ran out of memory.')
})

test('a new thread id resets the steps', () => {
  const first = toPanel(undefined, { ...base, steps: [{ seq: 1, tool: 'old_tool' }] })
  const next = toPanel(first, { ...base, id: 's2', steps: [{ seq: 1, tool: 'new_tool' }] })
  expect(next.steps.map(s => s.label)).toEqual(['New tool'])
})

test('parseToolResult reads JSON text, structured content, rejects errors and non-JSON', () => {
  const json = JSON.stringify({ ...base, cursor: 3 })
  expect(parseToolResult({ text: json })?.cursor).toBe(3)
  expect(parseToolResult({ result: { content: [{ type: 'text', text: json }] } })?.id).toBe('s1')
  expect(parseToolResult({ result: { structuredContent: base } })?.id).toBe('s1')
  expect(parseToolResult({ text: json, isError: true })).toBe(null)
  expect(parseToolResult({ text: 'boom' })).toBe(null)
})

test('a start result (no steps or cost) parses with defaults', () => {
  const s = parseToolResult({ text: '{"id":"s1","run_id":"r","state":"working","cursor":0}' })
  expect(s?.steps).toEqual([])
  expect(s?.cost_cents).toBe(0)
})

const text = (o: unknown) => ({ text: JSON.stringify(o) })
const done = toPanel(undefined, { ...base, state: 'done', summary: 'answer', steps: [{ seq: 1, tool: 't' }], cost_cents: 50 })

test('stepsView: Thinking while working with no steps, hidden when idle and empty', () => {
  expect(stepsView({ ...done, steps: [], state: 'working' })).toBe('thinking')
  expect(stepsView({ ...done, steps: [], state: 'done' })).toBe('none')
  expect(stepsView({ ...done, steps: [], state: 'failed' })).toBe('none')
  expect(stepsView({ ...done, state: 'done' })).toBe('steps')
})

test('reply on the same id starts a new turn, keeping cost', () => {
  const p = applyResult(done, 'reply', text({ id: 's1', run_id: 'r2', cursor: 9 }))
  expect(p).toMatchObject({ id: 's1', state: 'working', summary: null, steps: [], cost: '$0.50' })
})

test('reply for another id starts fresh', () => {
  const p = applyResult(done, 'reply', text({ id: 's2', run_id: 'r', cursor: 0 }))
  expect(p).toMatchObject({ id: 's2', state: 'working', steps: [], cost: '$0.00' })
  expect(applyResult(undefined, 'reply', text({ id: 's3', run_id: 'r' }))?.id).toBe('s3')
})

test('cancel marks cancelled and keeps steps', () => {
  const w = toPanel(undefined, { ...base, steps: [{ seq: 1, tool: 't' }] })
  const p = applyResult(w, 'cancel', text({ id: 's1', status: 'cancelled' }))
  expect(p?.state).toBe('cancelled')
  expect(p?.steps.map(s => s.label)).toEqual(['T'])
})

test('cancel for another id, not_generating, or errors are ignored', () => {
  expect(applyResult(done, 'cancel', text({ id: 'zz', status: 'cancelled' }))).toBe(null)
  expect(applyResult(done, 'cancel', text({ id: 's1', status: 'not_generating' }))).toBe(null)
  expect(applyResult(undefined, 'cancel', text({ id: 's1', status: 'cancelled' }))).toBe(null)
  expect(applyResult(done, 'cancel', { ...text({ id: 's1', status: 'cancelled' }), isError: true })).toBe(null)
  expect(applyResult(done, 'reply', { text: 'boom' })).toBe(null)
})

test('start/status go through toPanel', () => {
  expect(applyResult(undefined, 'status', text({ ...base, state: 'done', summary: 'x' }))?.summary).toBe('x')
})

test('bandView: working shows latest step or Thinking, with cost', () => {
  const w = toPanel(undefined, { ...base, cost_cents: 12 })
  expect(bandView(w, false)).toEqual({ state: 'working', label: 'Thinking…', cost: '$0.12' })
  const s = toPanel(w, { ...base, steps: [{ seq: 1, tool: 'a' }, { seq: 2, tool: 'search_nfcore_module' }] })
  expect(bandView(s, false)?.label).toBe('Search nfcore module')
})

test('bandView: ended states show state + cost until dismissed; null without activity', () => {
  expect(bandView(done, false)).toEqual({ state: 'done', label: 'done', cost: '$0.50' })
  expect(bandView({ ...done, state: 'failed' }, false)?.state).toBe('failed')
  expect(bandView({ ...done, state: 'cancelled' }, false)?.label).toBe('cancelled')
  expect(bandView(done, true)).toBe(null)
  expect(bandView(null, false)).toBe(null)
})

test('next prompt dismisses an ended band but not a working one', () => {
  expect(dismissOnPrompt(done, false)).toBe(true)
  expect(dismissOnPrompt({ ...done, state: 'working' }, false)).toBe(false)
  expect(dismissOnPrompt(null, false)).toBe(false)
  expect(bandView({ ...done, state: 'working' }, dismissOnPrompt({ ...done, state: 'working' }, false))).not.toBe(null)
})

test('reshowBand: only on new thread, state change, or a new turn', () => {
  const same = { ...done }
  expect(reshowBand(done, same, 'status')).toBe(false)
  expect(reshowBand(done, { ...done, state: 'failed' }, 'status')).toBe(true)
  expect(reshowBand(done, { ...done, id: 's2' }, 'status')).toBe(true)
  expect(reshowBand(undefined, done, 'status')).toBe(true)
  expect(reshowBand(done, same, 'start')).toBe(true)
  expect(reshowBand(done, same, 'reply')).toBe(true)
  expect(reshowBand(done, same, 'cancel')).toBe(false)
})

test('step labels come from tool names', () => {
  expect(stepLabel('call_seqera_api')).toBe('Call seqera api')
  expect(stepLabel('')).toBe('Working')
})

test('a follow-up that comes back done starts the steps over and shows the answer', () => {
  const prev = toPanel(undefined, { ...base, steps: [{ seq: 1, tool: 'old_step' }] })
  const p = applyResult(prev, 'reply', text({ ...base, state: 'done', summary: 'new answer', steps: [{ seq: 9, tool: 'skill' }], cursor: 9 }))
  expect(p?.state).toBe('done')
  expect(p?.summary).toBe('new answer')
  expect(p?.steps.map(s => s.label)).toEqual(['Skill'])
})

test('accepts thread_id results from the renamed tools', () => {
  const p = applyResult(undefined, 'start', text({ thread_id: 's9', state: 'done', steps: [], summary: 'answer', cost_cents: 4, cursor: 3 }))
  expect(p?.id).toBe('s9')
  expect(p?.state).toBe('done')
  const c = applyResult(p ?? undefined, 'cancel', text({ thread_id: 's9', status: 'cancelled' }))
  expect(c?.state).toBe('cancelled')
})
