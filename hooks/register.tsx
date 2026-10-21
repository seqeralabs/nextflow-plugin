import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import { applyResult, bandView, dismissOnPrompt, reshowBand, stepsView } from './panel'

const PANE = 'seqera-coscientist'
const PURPLE = '#201637'
const NF = '#0DC09D'
const GREEN = '#28AE61'
const AMBER = '#E0A100'
const RED = '#E5484D'

const panel = atom({ plugin: 'nextflow', key: 'coscientist' } as const, null)
const dismissed = atom({ plugin: 'nextflow', key: 'bandDismissed' } as const, false)

export const register: Register = on => {
  on('tool.call', { tool: /co_scientist_(start|status|reply|cancel)$/ }, async ($, e, next) => {
    const r = await next(e)
    const kind = /co_scientist_(\w+)$/.exec(String(e.tool))?.[1] as 'start' | 'status' | 'reply' | 'cancel'
    let reshow = false
    await update($, panel, prev => {
      const n = applyResult(prev ?? undefined, kind, r)
      reshow = n !== null && reshowBand(prev ?? undefined, n, kind)
      return n ?? prev
    })
    if (reshow) await update($, dismissed, () => false)
    return r
  }).catch(($, e, next) => next(e))

  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'co-scientist', description: 'Show co-scientist progress in a pane' })
    return next(e)
  })

  on('command.run', { command: 'co-scientist' }, async $ => {
    await $.ui.open({ id: PANE, title: 'Co-scientist' })
    return { text: 'Co-scientist pane opened.' }
  })

  on('prompt.submit', async ($, e, next) => {
    const p = await read($, panel)
    await update($, dismissed, d => dismissOnPrompt(p, d))
    return next(e)
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const b = bandView(await read($, panel), await read($, dismissed))
    if (e.props.hasSurvey || !b) return next(e)
    const { Box, Button, Text } = $.ui.resolve(e)
    return (
      <Box flexDirection="row">
        <Text>
          <Text backgroundColor={PURPLE} color={NF} weight="bold"> co-scientist </Text>
          <Text color={{ working: NF, done: GREEN, failed: RED, cancelled: AMBER }[b.state]}>  {b.state}</Text>
          <Text dimColor>  {b.state === 'working' ? b.label : ''}  </Text>
          <Text dimColor tabular>{b.cost}  </Text>
        </Text>
        <Button key="details" label="Details" onPress={() => $.ui.open({ id: PANE, title: 'Co-scientist' })} />
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e, next) => {
    const p = await read($, panel)
    if (!p) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const tone = { working: NF, done: GREEN, failed: RED, cancelled: AMBER }[p.state]
    return (
      <Box flexDirection="column" paddingX={1}>
        <Box flexDirection="row" justifyContent="space-between">
          <Text>
            <Text backgroundColor={PURPLE} color={NF} weight="bold"> co-scientist </Text>
            <Text weight="semibold">  {p.state === 'working' ? 'is working…' : p.state}</Text>
          </Text>
          <Text dimColor tabular>{p.cost}</Text>
        </Box>
        {stepsView(p) !== 'none' && (
          <Box flexDirection="column" borderStyle="round" borderColor={tone} paddingX={1} marginTop={1}>
            {stepsView(p) === 'thinking' && <Text dimColor>Thinking…</Text>}
            {p.steps.map((s, i) => (
              <Text key={`s${s.seq}`} dimColor={i < p.steps.length - 1 || p.state !== 'working'}>
                {i === p.steps.length - 1 && p.state === 'working' ? '▶' : '✔'} {s.label}
              </Text>
            ))}
          </Box>
        )}
        {p.state === 'failed' && <Text color={RED} wrap="wrap">{p.message}</Text>}
      </Box>
    )
  })
}
