# AGENTS.md

A Claude Code and Codex plugin of agent skills ([Agent Skills spec](https://agentskills.io/specification)) for building and running Nextflow pipelines, plus the Seqera MCP server. The deliverable is `skills/*/SKILL.md`; there is no build. Load locally with `claude --plugin-dir .`.

## Checks and releases

- Files listed in `sources.json` carry a `bundled_sha256`. After editing one, update its hash and set `override: true`, then run `python3 -I tools/check_sources.py` (CI runs it too).
- Releasing: bump `version` in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `.codex-plugin/plugin.json` together.
- After editing `.github/workflows/`, run `npx actions-up` and `zizmor`.

## Writing skills

- Write for any skills-compatible agent: describe actions in plain terms, without host-specific tool names, `allowed-tools`, or `${CLAUDE_PLUGIN_ROOT}` paths.
- Modules come from the **Nextflow Registry**; `nf-core` is one namespace in it (e.g. `nf-core/fastqc`).
- Include registry modules as Nextflow-managed modules (`from 'nf-core/fastqc'`); use local paths only for locally modified modules.
- Nextflow uses calendar versioning (`YY.MM.PATCH`), so `26.04.0` is newer than `25.10.1`. Pin with `NXF_VER`.

## Keep in sync

When changing one of these, update every skill that repeats it:

- Nextflow version requirements: 26.04+ for `nextflow module`, `auth` and `launch`; 26.10+ for workflow modules and `nextflow lint` type checking. Stated in `install-nextflow`, `run-module`, `launch-workflow`, `migrate-nextflow-code` and the `build-nextflow-pipeline` create-workflow reference.
- Registry module guidance shared by `run-module` and the create-workflow reference: the `kind=Workflow` registry query, untyped workflow module handling, and the Wave+Conda config block.
