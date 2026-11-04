declare module 'claude-code' {
  interface PluginState {
    nextflow: {
      coscientist: {
        id: string
        state: 'working' | 'done' | 'failed' | 'cancelled'
        steps: { seq: number; label: string }[]
        summary: string | null
        cost: string
      } | null
      bandDismissed: boolean
    }
  }
}
