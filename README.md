# Nextflow plugin for Claude and Codex

Build, migrate, test, debug and run [Nextflow](https://www.nextflow.io) pipelines with
Claude or Codex, connected to [Nextflow Platform](https://seqera.io), Wave containers and nf-core.

The plugin bundles 28 skills and the hosted Seqera MCP server (`https://mcp.seqera.io/mcp`).

## Install

In Claude Code:

```
/plugin marketplace add seqeralabs/nextflow-plugin
/plugin install nextflow@nextflow-plugin
```

Or from a shell:

```bash
claude plugin marketplace add seqeralabs/nextflow-plugin
claude plugin install nextflow@nextflow-plugin
```

Restart Claude Code after installing. The first time a Seqera tool is used, Claude Code opens
the Nextflow Platform sign-in (OAuth). Skills that only work with local files and Nextflow do
not need a Seqera account.

To make the plugin available to everyone working in a repository, add it to that repository's
`.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "nextflow-plugin": {
      "source": { "source": "github", "repo": "seqeralabs/nextflow-plugin" }
    }
  },
  "enabledPlugins": { "nextflow@nextflow-plugin": true }
}
```

### Codex

In the Codex app, open **Plugins → Add → Add plugin marketplace**, enter
`seqeralabs/nextflow-plugin` as the source and install **Nextflow**. Or from a shell:

```bash
codex plugin marketplace add seqeralabs/nextflow-plugin
codex plugin add nextflow@nextflow-plugin
```

The same repository serves both hosts: Codex reads the Claude marketplace and plugin layout,
and takes its listing (name, logo, starter prompts) from `.codex-plugin/plugin.json`.

### Skills only

The skills follow the [Agent Skills](https://agentskills.io/specification) specification, so
any skills-compatible agent (Claude Code, Codex, Cursor, OpenCode and others) can install them
without the plugin. Use [`npx skills`](https://github.com/vercel-labs/skills):

```bash
npx skills add seqeralabs/nextflow-plugin
```

Or the [GitHub CLI](https://cli.github.com/) (v2.90.0+):

```bash
gh skill install seqeralabs/nextflow-plugin
```

Both prompt for the skills and agents to install to. Update installed skills with
`npx skills update` or `gh skill update --all`.

Installing skills this way does not configure the Seqera MCP server. For skills that use
Nextflow Platform (e.g. `launch-workflow`), add `https://mcp.seqera.io/mcp` to your agent's
MCP configuration.

## What's included

| Area | Skills |
| --- | --- |
| Build pipelines | `build-nextflow-pipeline`, `nf-pipeline-design`, `nextflow-config`, `nextflow-schema`, `nextflow-output-patterns`, `search-existing-modules`, `run-module`, `create-container` |
| Convert to Nextflow | `build-nextflow-pipeline` (Python, R and notebook playbooks), `migrate-from-snakemake`, `audit-conversion-readiness`, `nextflow-schema` (parameter triage), `find-alternative-tools` |
| Migrate and modernise | `migrate-nextflow-code`, `nextflow-schema` (schema migration), `nf-plugin-development`, `nf-plugin-legacy-migration`, `maintain-nf-core-pipeline` |
| Test and debug | `nf-test` (authoring and failure repair), `repair-workflow` (including static diagnostics), `debug-local-run`, `debug-seqera-failed-run`, `nextflow-history` (history, cache and narrative recaps), `nf-data-lineage`, `nf-docker-scripts` |
| Nextflow Platform | `launch-workflow` (with shared MCP connection reference), `ce-credentials-setup`, `seqera-data-links`, `seqerakit` |
| General | `nextflow-development`, `install-nextflow` |

## Licensing

Licensed under the [Apache License, Version 2.0](LICENSE). Third-party attributions are in
[`NOTICE`](NOTICE), and per-file origin is recorded in [`sources.json`](sources.json).

The Apache-2.0 license covers the files in this repository. The hosted Seqera MCP server it
connects to is a separate work, governed by its own license and Seqera's terms of service.
