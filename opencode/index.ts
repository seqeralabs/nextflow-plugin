import type { Plugin as PluginV1 } from "@opencode-ai/plugin";
import type { Plugin as PluginV2 } from "@opencode/plugin";

import { registerSeqeraMcp, registerSkillPaths, setupV2 } from "./config.ts";

/**
 * opencode-nextflow:
 * Dual-compatible OpenCode 1.x and 2.x server plugin.
 *
 * In OpenCode 1.x:
 *   OpenCode invokes `server(input, options)` which hooks `config` to register
 *   `config.skills.paths` and `config.mcp.seqera`.
 *
 * In OpenCode 2.x:
 *   OpenCode invokes `setup(ctx)` which registers `seqera` via `ctx.mcp.transform`
 *   and all 28 bundled skills via `ctx.skill.transform`.
 *
 * Options (both 1.x and 2.x):
 *   { skills: false }               — disable all bundled skills
 *   { skills: { "<name>": false } } — disable one bundled skill
 *   { mcp: false }                  — skip Seqera MCP registration
 */
const server: PluginV1 = async (_input, options) => {
  return {
    config: async (config) => {
      registerSkillPaths(config, options);
      registerSeqeraMcp(config, options);
    },
  };
};

const setup: PluginV2.Plugin["setup"] = async (ctx) => {
  await setupV2(ctx);
};

export default {
  id: "nextflow",
  server, // OpenCode 1.x entry point
  setup, // OpenCode 2.x entry point
};
