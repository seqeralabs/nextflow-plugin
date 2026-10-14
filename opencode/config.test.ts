import { describe, expect, test } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  discoverBundledSkills,
  type McpEditorV2,
  parseFrontmatter,
  parseSkill,
  type PluginContextV2,
  registerSeqeraMcp,
  registerSkillPaths,
  resolveEnabledSkills,
  SEQERA_MCP_URL,
  setupV2,
  type SkillEditorV2,
} from "./config.ts";
import plugin from "./index.ts";

function fixtureRoot(skills: string[]): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "nextflow-skills-"));
  for (const skill of skills) {
    fs.mkdirSync(path.join(root, skill), { recursive: true });
    fs.writeFileSync(
      path.join(root, skill, "SKILL.md"),
      `---\nname: ${skill}\ndescription: >\n  Fixture for ${skill}\n---\n# ${skill}\n\nInstructions.\n`,
    );
  }
  fs.mkdirSync(path.join(root, "not-a-skill"));
  return root;
}

const deps = (root: string) => ({ skillsRoot: root });

describe("discoverBundledSkills", () => {
  test("finds only directories containing SKILL.md", () => {
    const root = fixtureRoot(["aaa", "bbb"]);
    expect(discoverBundledSkills(root)).toEqual(["aaa", "bbb"]);
  });

  test("missing root yields empty list", () => {
    expect(discoverBundledSkills(path.join(os.tmpdir(), "nextflow-missing-root"))).toEqual([]);
  });
});

describe("resolveEnabledSkills", () => {
  const names = ["aaa", "bbb"];

  test("defaults to all skills", () => {
    expect(resolveEnabledSkills(names, undefined)).toEqual(names);
  });

  test("false disables all", () => {
    expect(resolveEnabledSkills(names, { skills: false })).toEqual([]);
  });

  test("per-skill opt-out", () => {
    expect(resolveEnabledSkills(names, { skills: { aaa: false } })).toEqual(["bbb"]);
  });

  test("unknown skill names are silently ignored", () => {
    expect(resolveEnabledSkills(names, { skills: { nope: false } })).toEqual(names);
  });
});

describe("parseFrontmatter and parseSkill", () => {
  test("parses folded description and autoinvoke flags", () => {
    const fm = `name: sample-skill
description: >
  A multi-line
  folded description.
metadata:
  opencode/autoinvoke: "false"`;
    const parsed = parseFrontmatter(fm);
    expect(parsed.name).toBe("sample-skill");
    expect(parsed.description).toBe("A multi-line folded description.");
    expect(parsed.autoinvoke).toBe(false);
  });

  test("parses a fixture SKILL.md file completely", () => {
    const root = fixtureRoot(["my-test-skill"]);
    const skill = parseSkill(root, "my-test-skill");
    expect(skill.id).toBe("my-test-skill");
    expect(skill.name).toBe("my-test-skill");
    expect(skill.description).toBe("Fixture for my-test-skill");
    expect(skill.content).toBe("# my-test-skill\n\nInstructions.");
    expect(skill.path).toBe(path.join(root, "my-test-skill", "SKILL.md"));
  });
});

describe("OpenCode 1.x: registerSkillPaths", () => {
  test("appends absolute skill paths without duplicates", () => {
    const root = fixtureRoot(["aaa", "bbb"]);
    const config: Record<string, unknown> = {};
    registerSkillPaths(config, undefined, deps(root));
    registerSkillPaths(config, undefined, deps(root));
    expect(config).toEqual({ skills: { paths: [path.join(root, "aaa"), path.join(root, "bbb")] } });
  });

  test("respects per-skill opt-out", () => {
    const root = fixtureRoot(["aaa", "bbb"]);
    const config: Record<string, unknown> = {};
    registerSkillPaths(config, { skills: { bbb: false } }, deps(root));
    expect(config).toEqual({ skills: { paths: [path.join(root, "aaa")] } });
  });
});

describe("OpenCode 1.x: registerSeqeraMcp", () => {
  test("registers the hosted server", () => {
    const config: Record<string, unknown> = {};
    registerSeqeraMcp(config, undefined);
    expect(config).toEqual({ mcp: { seqera: { type: "remote", url: SEQERA_MCP_URL } } });
  });

  test("never overrides an explicit user entry", () => {
    const mine = { type: "remote", url: "https://example.test/mcp" };
    const config: Record<string, unknown> = { mcp: { seqera: mine } };
    registerSeqeraMcp(config, undefined);
    expect((config.mcp as Record<string, unknown>)["seqera"]).toBe(mine);
  });

  test("populates default url and type when user provides partial options", () => {
    const config: Record<string, unknown> = { mcp: { seqera: { enabled: true } } };
    registerSeqeraMcp(config, undefined);
    expect(config).toEqual({ mcp: { seqera: { enabled: true, type: "remote", url: SEQERA_MCP_URL } } });
  });

  test("mcp: false skips registration", () => {
    const config: Record<string, unknown> = {};
    registerSeqeraMcp(config, { mcp: false });
    expect(config).toEqual({});
  });
});

describe("OpenCode 2.x: setupV2", () => {
  function makeMockContext(options?: unknown): {
    ctx: PluginContextV2;
    mcpStore: Map<string, Record<string, unknown>>;
    skillStore: Map<string, Record<string, unknown>>;
  } {
    const mcpStore = new Map<string, Record<string, unknown>>();
    const skillStore = new Map<string, Record<string, unknown>>();

    const mcpEditor: McpEditorV2 = {
      get: (name) => mcpStore.get(name),
      set: (name, cfg) => {
        mcpStore.set(name, { ...cfg });
      },
      update: (name, fn) => {
        const item = mcpStore.get(name);
        if (item) fn(item);
      },
    };

    const skillEditor: SkillEditorV2 = {
      get: (id) => skillStore.get(id),
      add: (s) => {
        skillStore.set(s.id, { ...s });
      },
      update: (id, fn) => {
        const item = skillStore.get(id);
        if (item) fn(item);
      },
      remove: (id) => {
        skillStore.delete(id);
      },
    };

    const ctx: PluginContextV2 = {
      options,
      mcp: {
        transform: async (cb) => cb(mcpEditor),
      },
      skill: {
        transform: async (cb) => cb(skillEditor),
      },
    };

    return { ctx, mcpStore, skillStore };
  }

  test("registers seqera MCP server and all bundled skills in 2.x", async () => {
    const root = fixtureRoot(["aaa", "bbb"]);
    const { ctx, mcpStore, skillStore } = makeMockContext();

    await setupV2(ctx, deps(root));

    expect(mcpStore.get("seqera")).toEqual({ type: "remote", url: SEQERA_MCP_URL });
    expect(skillStore.has("aaa")).toBe(true);
    expect(skillStore.has("bbb")).toBe(true);
    expect(skillStore.get("aaa")?.description).toBe("Fixture for aaa");
  });

  test("honors mcp: false in 2.x", async () => {
    const root = fixtureRoot(["aaa"]);
    const { ctx, mcpStore } = makeMockContext({ mcp: false });

    await setupV2(ctx, deps(root));
    expect(mcpStore.has("seqera")).toBe(false);
  });

  test("honors skills: false in 2.x", async () => {
    const root = fixtureRoot(["aaa", "bbb"]);
    const { ctx, skillStore } = makeMockContext({ skills: false });

    await setupV2(ctx, deps(root));
    expect(skillStore.size).toBe(0);
  });

  test("honors per-skill opt-out in 2.x", async () => {
    const root = fixtureRoot(["aaa", "bbb"]);
    const { ctx, skillStore } = makeMockContext({ skills: { aaa: false } });

    await setupV2(ctx, deps(root));
    expect(skillStore.has("aaa")).toBe(false);
    expect(skillStore.has("bbb")).toBe(true);
  });

  test("does not overwrite an existing skill in 2.x", async () => {
    const root = fixtureRoot(["aaa"]);
    const { ctx, skillStore } = makeMockContext();
    skillStore.set("aaa", { id: "aaa", name: "custom-aaa" });

    await setupV2(ctx, deps(root));
    expect(skillStore.get("aaa")?.name).toBe("custom-aaa");
  });
});

describe("dual export structure", () => {
  test("exports id, 1.x server, and 2.x setup", () => {
    expect(plugin.id).toBe("nextflow");
    expect(typeof plugin.server).toBe("function");
    expect(typeof plugin.setup).toBe("function");
  });
});

describe("real skills tree", () => {
  test("discovers all 28 bundled skills", () => {
    expect(discoverBundledSkills()).toHaveLength(28);
  });
});
