export type Status = {
  id: string
  state: 'working' | 'done' | 'failed' | 'cancelled'
  steps: { seq: number; tool: string }[]
  summary: string | null
  cost_cents: number
  cursor: number
}
export type PanelState = {
  id: string
  state: Status['state']
  steps: { seq: number; label: string }[]
  summary: string | null
  cost: string
}

// Portal sends raw tool names; the band shows them as words.
export function stepLabel(tool: string): string {
  const words = tool.replace(/_/g, ' ').trim()
  return words ? words[0].toUpperCase() + words.slice(1) : 'Working'
}

export function toPanel(prev: PanelState | undefined, s: Status): PanelState {
  const kept = prev && prev.id === s.id ? prev.steps : []
  const seen = new Set(kept.map(x => x.seq))
  const added = s.steps.filter(x => !seen.has(x.seq)).map(x => ({ seq: x.seq, label: stepLabel(x.tool) }))
  return {
    id: s.id,
    state: s.state,
    summary: s.summary,
    steps: [...kept, ...added],
    cost: `$${(s.cost_cents / 100).toFixed(2)}`,
  }
}

const STATES = ['working', 'done', 'failed', 'cancelled']

// Accepts a tool.call result: { text }, { result: <string | object | MCP content> }; null on error or non-status JSON.
function unwrap(result: unknown): unknown {
  const r = result as { isError?: boolean; deny?: string; text?: unknown; result?: unknown } | null
  if (!r || typeof r !== 'object' || r.isError || r.deny !== undefined) return null
  let v: unknown = r.text ?? r.result
  if (v && typeof v === 'object') {
    const m = v as { isError?: boolean; structuredContent?: unknown; content?: { type?: string; text?: string }[] }
    if (m.isError) return null
    if (m.structuredContent) v = m.structuredContent
    else if (Array.isArray(m.content)) v = m.content.find(c => c.type === 'text')?.text
  }
  if (typeof v === 'string') {
    try {
      v = JSON.parse(v)
    } catch {
      return null
    }
  }
  return v
}

export function parseToolResult(result: unknown): Status | null {
  const s = unwrap(result) as Partial<Status> | null
  if (!s || typeof s !== 'object' || typeof s.id !== 'string' || !STATES.includes(s.state as string)) return null
  return {
    id: s.id,
    state: s.state as Status['state'],
    steps: s.steps ?? [],
    summary: s.summary ?? null,
    cost_cents: s.cost_cents ?? 0,
    cursor: s.cursor ?? 0,
  }
}

const EMPTY_COST = '$0.00'

export function stepsView(p: PanelState): 'steps' | 'thinking' | 'none' {
  if (p.steps.length) return 'steps'
  return p.state === 'working' ? 'thinking' : 'none'
}

// Returns the next panel state for a start/status/reply/cancel tool result, or null for "no change".
export function applyResult(prev: PanelState | undefined, tool: 'start' | 'status' | 'reply' | 'cancel', result: unknown): PanelState | null {
  const s = parseToolResult(result)
  if (s && tool !== 'cancel') return toPanel(tool === 'reply' ? undefined : prev, s)
  if (tool === 'start' || tool === 'status') return null
  const v = unwrap(result) as { id?: unknown; status?: unknown } | null
  if (!v || typeof v !== 'object' || typeof v.id !== 'string') return null
  if (tool === 'reply') {
    const cost = prev && prev.id === v.id ? prev.cost : EMPTY_COST
    return { id: v.id, state: 'working', steps: [], summary: null, cost }
  }
  return prev && prev.id === v.id && v.status === 'cancelled' ? { ...prev, state: 'cancelled' } : null
}

export type Band = { state: Status['state']; label: string; cost: string }

// What the one-line band shows: null when there is nothing to draw (no activity, or an ended run already dismissed).
export function bandView(p: PanelState | null, dismissed: boolean): Band | null {
  if (!p || (dismissed && p.state !== 'working')) return null
  const label = p.state === 'working' ? (p.steps[p.steps.length - 1]?.label ?? 'Thinking…') : p.state
  return { state: p.state, label, cost: p.cost }
}

// The next prompt clears an ended run's band; a working run keeps it.
export function dismissOnPrompt(p: PanelState | null, dismissed: boolean): boolean {
  return dismissed || (p !== null && p.state !== 'working')
}

// Whether a tool result should bring back a dismissed band: new thread, state change, or a new turn (start/reply).
export function reshowBand(prev: PanelState | undefined, next: PanelState, tool: 'start' | 'status' | 'reply' | 'cancel'): boolean {
  return tool === 'start' || tool === 'reply' || !prev || prev.id !== next.id || prev.state !== next.state
}
