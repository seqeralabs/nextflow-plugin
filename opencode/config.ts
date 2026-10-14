import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const SEQERA_MCP_URL = "https://mcp.seqera.io/mcp";

/** Directory holding the bundled `skills/<name>/SKILL.md` tree. */
export function defaultSkillsRoot(): string {
  return path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../skills");
}

export type Deps = {
  skillsRoot?: string;
};

export type ParsedSkill = {
  id: string;
  name: string;
  description?: string;
  autoinvoke?: boolean;
  path: string;
  content: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function pluginOption(options: unknown, key: "skills" | "mcp"): unknown {
  if (!isRecord(options) || !(key in options)) return undefined;
  return options[key];
}

/** Fill in hosted Seqera defaults on an entry that lacks its own transport. */
function ensureSeqeraEntry(existing: unknown): Record<string, unknown> {
  if (isRecord(existing) && (existing.url || existing.command)) return existing;
  if (isRecord(existing)) {
    existing.type ??= "remote";
    existing.url = SEQERA_MCP_URL;
    return existing;
  }
  return { type: "remote", url: SEQERA_MCP_URL };
}

/** Parse frontmatter fields from a SKILL.md file. */
export function parseFrontmatter(fm: string): { name?: string; description?: string; autoinvoke?: boolean } {
  const lines = fm.split(/\r?\n/);
  let name: string | undefined;
  let description: string | undefined;
  let autoinvoke: boolean | undefined;

  let currentKey: string | null = null;
  const currentLines: string[] = [];

  const flush = () => {
    if (currentKey === "name") {
      name = currentLines.join(" ").trim();
    } else if (currentKey === "description") {
      description = currentLines.join(" ").trim();
    }
    currentLines.length = 0;
  };

  for (const line of lines) {
    const keyMatch = line.match(/^([a-zA-Z0-9_/-]+):\s*(.*)$/);
    if (keyMatch) {
      flush();
      currentKey = keyMatch[1];
      const val = keyMatch[2].trim();
      if (currentKey === "name") {
        currentLines.push(val);
      } else if (currentKey === "description" && val && !/^(\>|\|)-?$/.test(val)) {
        currentLines.push(val);
      }
    } else if (currentKey && /^\s+/.test(line)) {
      currentLines.push(line.trim());
    }
    if (line.includes("opencode/autoinvoke") && line.includes("false")) {
      autoinvoke = false;
    }
  }
  flush();

  return { name, description, autoinvoke };
}

/** Read and parse a bundled SKILL.md into a structured skill record. */
export function parseSkill(root: string, name: string): ParsedSkill {
  const skillPath = path.join(root, name, "SKILL.md");
  let text: string;
  try {
    text = fs.readFileSync(skillPath, "utf8");
  } catch {
    return { id: name, name, path: skillPath, content: "" };
  }

  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!match) {
    return { id: name, name, path: skillPath, content: text.trim() };
  }

  const [, fm, body] = match;
  const parsed = parseFrontmatter(fm);

  return {
    id: name,
    name: parsed.name || name,
    description: parsed.description || undefined,
    autoinvoke: parsed.autoinvoke,
    path: skillPath,
    content: body.trim(),
  };
}

/** Skill directories present in the bundle (must contain SKILL.md). */
export function discoverBundledSkills(skillsRoot: string = defaultSkillsRoot()): string[] {
  let entries: string[];
  try {
    entries = fs.readdirSync(skillsRoot);
  } catch {
    return [];
  }
  return entries
    .filter((name) => !name.startsWith("."))
    .filter((name) => fs.existsSync(path.join(skillsRoot, name, "SKILL.md")))
    .sort();
}

export function resolveEnabledSkills(skillNames: string[], options: unknown): string[] {
  const value = pluginOption(options, "skills");
  if (value === false) return [];
  if (value === undefined || typeof value === "boolean" || !isRecord(value)) return [...skillNames];
  return skillNames.filter((skill) => value[skill] !== false);
}

// ============================================================================
// OpenCode 1.x Hook Handlers
// ============================================================================

type ConfigWithSkills = {
  skills?: {
    paths?: string[];
  } & Record<string, unknown>;
} & Record<string, unknown>;

/** OpenCode 1.x: append bundled skill directories to `config.skills.paths`. */
export function registerSkillPaths(config: object, options: unknown, deps: Deps = {}): void {
  const root = deps.skillsRoot ?? defaultSkillsRoot();
  const skills = resolveEnabledSkills(discoverBundledSkills(root), options);
  const cfg = config as ConfigWithSkills;

  if (!isRecord(cfg.skills)) cfg.skills = {};
  const paths = Array.isArray(cfg.skills.paths) ? cfg.skills.paths : (cfg.skills.paths = []);
  for (const skill of skills) {
    const skillPath = path.join(root, skill);
    if (!paths.includes(skillPath)) {
      paths.push(skillPath);
    }
  }
}

type ConfigWithMcp = {
  mcp?: Record<string, unknown>;
} & Record<string, unknown>;

/** OpenCode 1.x: register the hosted Seqera MCP server under `config.mcp.seqera`. */
export function registerSeqeraMcp(config: object, options: unknown): void {
  if (pluginOption(options, "mcp") === false) return;
  const cfg = config as ConfigWithMcp;
  if (!isRecord(cfg.mcp)) cfg.mcp = {};
  cfg.mcp["seqera"] = ensureSeqeraEntry(cfg.mcp["seqera"]);
}

// ============================================================================
// OpenCode 2.x Transform Handlers
// ============================================================================

export type McpEditorV2 = {
  get(name: string): Record<string, unknown> | undefined;
  set(name: string, config: Record<string, unknown>): void;
  update(name: string, update: (config: Record<string, unknown>) => void): void;
};

export type SkillEditorV2 = {
  get(id: string): Record<string, unknown> | undefined;
  add(skill: ParsedSkill): void;
  update(id: string, update: (skill: Record<string, unknown>) => void): void;
  remove(id: string): void;
};

export type PluginContextV2 = {
  options?: unknown;
  mcp?: {
    transform(callback: (editor: McpEditorV2) => void): Promise<unknown>;
  };
  skill?: {
    transform(callback: (editor: SkillEditorV2) => void): Promise<unknown>;
  };
};

/** OpenCode 2.x setup function. Registers Seqera MCP and all bundled skills. */
export async function setupV2(ctx: PluginContextV2, deps: Deps = {}): Promise<void> {
  const options = ctx.options;

  // 1. Seqera MCP server
  if (pluginOption(options, "mcp") !== false && ctx.mcp?.transform) {
    await ctx.mcp.transform((editor) => {
      editor.set("seqera", ensureSeqeraEntry(editor.get("seqera")));
    });
  }

  // 2. Bundled skills
  if (pluginOption(options, "skills") !== false && ctx.skill?.transform) {
    const root = deps.skillsRoot ?? defaultSkillsRoot();
    const enabled = resolveEnabledSkills(discoverBundledSkills(root), options);

    await ctx.skill.transform((editor) => {
      for (const name of enabled) {
        if (!editor.get(name)) {
          editor.add(parseSkill(root, name));
        }
      }
    });
  }
}
