#!/usr/bin/env python3
"""Verify that bundled files match the hashes recorded in sources.json and that manifests agree."""

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# The plugin directory submitted to the Claude plugin directory. sources.json paths are relative to it.
PLUGIN = REPO / "plugins" / "nextflow"

# The plugin directory only accepts these file types from unverified organizations.
ALLOWED_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"}
ALLOWED_NAMES = {"LICENSE", "NOTICE"}


def main() -> int:
    errors = []

    sources = json.loads((REPO / "sources.json").read_text())
    for entry in sources["files"]:
        path = PLUGIN / entry["path"]
        if not path.is_file():
            errors.append(f"missing bundled file: {entry['path']}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["bundled_sha256"]:
            errors.append(f"hash mismatch: {entry['path']}")

    plugin = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    codex = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    marketplace = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    entries = [p for p in marketplace["plugins"] if p["name"] == plugin["name"]]
    if len(entries) != 1:
        errors.append(f"marketplace must list plugin {plugin['name']} exactly once")
    elif entries[0].get("version") != plugin["version"]:
        errors.append(f"version mismatch: plugin.json {plugin['version']} vs marketplace {entries[0].get('version')}")
    elif entries[0].get("source") != "./" + PLUGIN.relative_to(REPO).as_posix():
        errors.append(f"marketplace source must be ./{PLUGIN.relative_to(REPO).as_posix()}")
    if codex.get("version") != plugin["version"]:
        errors.append(f"version mismatch: plugin.json {plugin['version']} vs .codex-plugin {codex.get('version')}")

    for path in sorted(PLUGIN.rglob("*")):
        if not path.is_file() or path.name == ".DS_Store" or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(PLUGIN).as_posix()
        if path.suffix.lower() not in ALLOWED_SUFFIXES and path.name not in ALLOWED_NAMES:
            errors.append(f"file type not accepted by the plugin directory: {rel}")
        elif path.read_bytes().startswith(b"#!"):
            errors.append(f"file starts with #!, not accepted by the plugin directory: {rel}")

    for skill in sorted((PLUGIN / "skills").iterdir()):
        if skill.is_dir() and not (skill / "SKILL.md").is_file():
            errors.append(f"skill directory without SKILL.md: {skill.name}")

    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    print(f"checked {len(sources['files'])} files, {len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
