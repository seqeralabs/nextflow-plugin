#!/usr/bin/env python3
"""Import a built Agent Plugins package (directory or .zip) into this repo as a Claude Code plugin.

The generic package is produced elsewhere from private sources. This script copies its
host-neutral content (skills, assets, licenses) into the plugin directory plugins/nextflow/,
provenance into the repo root, and regenerates the Claude-specific manifests, so this repo never needs access to those sources.

Usage:
    python3 -I tools/import_package.py /path/to/nextflow.zip
    python3 -I tools/import_package.py /path/to/nextflow/
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# The plugin directory submitted to the Claude plugin directory. sources.json paths are relative to it.
PLUGIN = REPO / "plugins" / "nextflow"

# Content copied verbatim from the generic package. Everything else in the package
# (plugin.json, mcp.json, .codex-plugin/, README.md) is host-specific and regenerated here.
CONTENT = ["skills", "assets", "licenses"]

# Files the Claude plugin directory rejects from unverified organizations (code, scripts,
# package-manager files, non-image assets). Their content is rewritten as Markdown in the
# skills that used them, so drop them on import. Paths are relative to the plugin directory.
# Allowed data files that lived beside removed code; moved before REMOVED_PATHS is applied.
MOVED_PATHS = {
    "skills/nextflow-development/scripts/config": "skills/nextflow-development/references/config",
}

REMOVED_PATHS = [
    "assets/nextflow.svg",
    "skills/nextflow-development/requirements.txt",
    "skills/nextflow-development/scripts",
    "skills/nf-pipeline-design/example_pipeline",
    "skills/nf-pipeline-design/scripts",
]

REPOSITORY = "https://github.com/seqeralabs/nextflow-plugin"
LICENSE = "Apache-2.0"

# Seqera releases the portal-derived skill files bundled in this plugin under Apache-2.0
# (the portal itself stays under BSL-1.1), so the portal license file is not distributed.
PORTAL_LICENSE = "licenses/portal-BSL-1.1.txt"
AUTHOR = {"name": "Seqera", "url": "https://seqera.io"}
PRIVACY_POLICY = "https://seqera.io/privacy-policy/"

# Version of the Claude plugin. It is released independently of the generic package
# because the Claude build curates the skill set below; bump it on every release.
VERSION = "0.2.2"

# Skills from the generic package that are not shipped in the Claude plugin.
EXCLUDED_SKILLS = [
    "enumerate-alternative-tools",  # duplicate of find-alternative-tools
    "generate-pipeline-docs",
    "generate-pipeline-memory",
    "genomics-workflow-acceleration",
    "nf-aggregate",
    "nf-pipeline-structure",  # folded into nf-pipeline-design
    "nf-storedir",
    "parabricks",
    "seqera-cli-agent",
]

# Product names renamed throughout the shipped skills and the plugin description.
RENAMES = [("Seqera Platform", "Nextflow Platform")]

# Exact text edits so the remaining skills don't point at excluded ones. Each edit must
# match exactly once, so upstream wording changes fail the import instead of slipping through.
EDITS = [
    ("skills/audit-conversion-readiness/SKILL.md",
     "- `enumerate-alternative-tools` — tools blocked by license, GPU",
     "- `find-alternative-tools` — tools blocked by license, GPU"),
    ("skills/audit-conversion-readiness/references/tool-availability.md",
     "`enumerate-alternative-tools` for a CPU path.",
     "`find-alternative-tools` for a CPU path."),
    ("skills/nf-pipeline-design/SKILL.md",
     "- `enumerate-alternative-tools` — tool choice at a branch",
     "- `find-alternative-tools` — tool choice at a branch"),
    ("skills/nf-pipeline-design/SKILL.md",
     """  shape", "tuple shape", "operator vs module". Pair with `nf-pipeline-structure`
  (which analyzes existing pipelines); this skill prescribes the rules for
  writing them. Use this skill before writing any new `.nf` file in an
  unfamiliar layout.""",
     """  shape", "tuple shape", "operator vs module". Also use it to analyze how an
  existing pipeline is organized — processes, modules, subworkflows, channels
  and data flow — when the user asks how a pipeline works or before changing
  it. Use this skill before writing any new `.nf` file in an unfamiliar layout."""),
    ("skills/maintain-nf-core-pipeline/SKILL.md",
     "- `nf-pipeline-structure`",
     "- `nf-pipeline-design`"),
    ("skills/nf-docker-scripts/SKILL.md",
     "- `nf-pipeline-structure` — understanding pipeline layout including shared helper commands",
     "- `nf-pipeline-design` — understanding pipeline layout including shared helper commands"),
    ("skills/nf-plugin-development/SKILL.md",
     "- `nf-pipeline-structure` — Standard pipeline organization",
     "- `nf-pipeline-design` — Standard pipeline organization"),
]
MCP_URL = "https://mcp.seqera.io/mcp"

# Listing icon shown in plugin browsers and the plugin directory.
ICON = "./assets/nextflow-uploaded-logo.png"


def locate_package(source: Path, workdir: Path) -> Path:
    if source.is_file():
        with zipfile.ZipFile(source) as archive:
            for member in archive.namelist():
                target = (workdir / member).resolve()
                if not target.is_relative_to(workdir.resolve()):
                    sys.exit(f"refusing unsafe archive member: {member}")
            archive.extractall(workdir)
        source = workdir
    if (source / "plugin.json").is_file():
        return source
    candidates = [p.parent for p in source.glob("*/plugin.json")]
    if len(candidates) != 1:
        sys.exit(f"expected exactly one package with plugin.json under {source}, found {len(candidates)}")
    return candidates[0]


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def relicense_portal_files() -> None:
    (PLUGIN / PORTAL_LICENSE).unlink(missing_ok=True)
    path = REPO / "sources.json"
    sources = json.loads(path.read_text())
    files = []
    for entry in sources["files"]:
        if entry["path"] != PORTAL_LICENSE:
            files.append(entry)
    sources["files"] = files
    sources["relicensed"] = {
        "sources": "portal",
        "from": "BUSL-1.1",
        "to": LICENSE,
        "by": "Seqera Labs, S.L.",
        "note": "Portal-derived files bundled in this plugin are distributed under Apache-2.0; see LICENSE and NOTICE.",
    }
    write_json(path, sources)


def rename(text: str) -> str:
    for old, new in RENAMES:
        text = text.replace(old, new)
    return text


def curate_skills() -> None:
    for skill in EXCLUDED_SKILLS:
        path = PLUGIN / "skills" / skill
        if not path.is_dir():
            sys.exit(f"excluded skill not found in package: {skill}")
        shutil.rmtree(path)

    edited = set()
    for rel, old, new in EDITS:
        path = PLUGIN / rel
        text = path.read_text()
        if text.count(old) != 1:
            sys.exit(f"edit for {rel} matched {text.count(old)} times; update EDITS")
        path.write_text(text.replace(old, new))
        edited.add(rel)

    for path in sorted((PLUGIN / "skills").rglob("*")):
        if not path.is_file() or path.suffix not in (".md", ".txt", ".py", ".sh", ".json", ".yml", ".yaml"):
            continue
        text = path.read_text()
        renamed = rename(text)
        if renamed != text:
            path.write_text(renamed)
            edited.add(path.relative_to(PLUGIN).as_posix())

    for old, new in MOVED_PATHS.items():
        if (PLUGIN / old).exists():
            shutil.rmtree(PLUGIN / new, ignore_errors=True)
            shutil.move(PLUGIN / old, PLUGIN / new)

    for rel in REMOVED_PATHS:
        path = PLUGIN / rel
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)

    for skill in EXCLUDED_SKILLS:
        for path in (PLUGIN / "skills").rglob("*"):
            if path.is_file() and f"`{skill}`" in path.read_text(errors="ignore"):
                sys.exit(f"{path.relative_to(PLUGIN)} still references excluded skill {skill}; add an edit")

    path = REPO / "sources.json"
    sources = json.loads(path.read_text())
    files = []
    for entry in sources["files"]:
        for old, new in MOVED_PATHS.items():
            if entry["path"].startswith(old + "/"):
                entry["path"] = new + entry["path"][len(old):]
        if entry["path"].split("/")[:2] in [["skills", s] for s in EXCLUDED_SKILLS]:
            continue
        if any(entry["path"] == rel or entry["path"].startswith(rel + "/") for rel in REMOVED_PATHS):
            continue
        if entry["path"] in edited:
            entry["bundled_sha256"] = hashlib.sha256((PLUGIN / entry["path"]).read_bytes()).hexdigest()
            entry["override"] = True
        files.append(entry)
    sources["files"] = files
    sources["claude_curation"] = {
        "excluded_skills": EXCLUDED_SKILLS,
        "removed_paths": REMOVED_PATHS,
        "renames": [{"from": old, "to": new} for old, new in RENAMES],
        "edited_files": sorted(edited),
    }
    write_json(path, sources)


def apply_curated_overlays() -> None:
    """Replay directory-compatible replacements after upstream curation/consolidation.

    Preserve upstream origin for replaced files; record repository origin for new
    guides. Overlay assets are authoritative and must be edited with their bundle.
    """
    overlays = REPO / "tools" / "curation" / "overlays"
    sources_path = REPO / "sources.json"
    sources = json.loads(sources_path.read_text())
    entries = {entry["path"]: entry for entry in sources["files"]}
    paths = []
    for asset in sorted(overlays.rglob("*.md")):
        rel = asset.relative_to(overlays).as_posix()
        destination = PLUGIN / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(asset, destination)
        digest = hashlib.sha256(asset.read_bytes()).hexdigest()
        entry = entries.get(rel)
        if entry is None:
            entry = {"path": rel,
                     "source": asset.relative_to(REPO).as_posix(),
                     "source_sha256": digest}
            sources["files"].append(entry)
        if entry["source"] == asset.relative_to(REPO).as_posix():
            entry["source_sha256"] = digest
        entry.update(bundled_sha256=digest, override=True)
        paths.append(rel)
    sources.setdefault("claude_curation", {})["overlay_files"] = paths
    write_json(sources_path, sources)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="generic package directory or .zip")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        package = locate_package(args.source.resolve(), Path(tmp))
        generic = json.loads((package / "plugin.json").read_text())

        for name in CONTENT:
            src, dst = package / name, PLUGIN / name
            if not src.exists():
                sys.exit(f"package is missing {name}")
            if dst.is_dir():
                shutil.rmtree(dst)
            elif dst.exists():
                dst.unlink()
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        if not (package / "sources.json").is_file():
            sys.exit("package is missing sources.json")
        shutil.copy2(package / "sources.json", REPO / "sources.json")

        relicense_portal_files()
        curate_skills()
        subprocess.run([
            sys.executable, "-I", str(REPO / "tools" / "consolidate_skills.py"),
            "--root", str(PLUGIN), "--sources", str(REPO / "sources.json"),
        ], check=True)

        apply_curated_overlays()

        codex = json.loads((package / ".codex-plugin" / "plugin.json").read_text())

        review = generic.get("extensions", {}).get("com.openai", {}).get("review", {}).get("test_cases")
        if review:
            write_json(REPO / "evals" / "review-cases.json", review)

    name, version, description = generic["name"], VERSION, rename(generic["description"])

    write_json(PLUGIN / ".claude-plugin" / "plugin.json", {
        "name": name,
        "version": version,
        "description": description,
        "icon": ICON,
        "author": AUTHOR,
        "homepage": REPOSITORY,
        "repository": REPOSITORY,
        "license": LICENSE,
        "privacyPolicyUrl": PRIVACY_POLICY,
        "keywords": generic.get("keywords", []),
    })

    write_json(REPO / ".claude-plugin" / "marketplace.json", {
        "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
        "name": "nextflow-plugin",
        "owner": AUTHOR,
        "metadata": {"description": "Nextflow plugin for Claude Code"},
        "plugins": [{
            "name": name,
            "source": "./" + PLUGIN.relative_to(REPO).as_posix(),
            "description": description,
            "version": version,
            "author": AUTHOR,
            "homepage": REPOSITORY,
            "license": LICENSE,
            "category": "development",
            "keywords": generic.get("keywords", []),
        }],
    })

    # Codex reads .claude-plugin/marketplace.json and the Claude plugin layout, but takes its
    # listing (display name, logo, brand colour, starter prompts) from this overlay.
    interface = dict(codex["interface"])
    for key in ("displayName", "shortDescription", "longDescription"):
        interface[key] = rename(interface[key])
    interface["defaultPrompt"] = [rename(prompt) for prompt in interface.get("defaultPrompt", [])]
    interface["developerName"] = AUTHOR["name"]
    interface["websiteURL"] = REPOSITORY
    interface["logo"] = ICON
    interface["composerIcon"] = ICON
    write_json(PLUGIN / ".codex-plugin" / "plugin.json", {
        "name": name,
        "version": version,
        "description": description,
        "author": AUTHOR,
        "homepage": REPOSITORY,
        "repository": REPOSITORY,
        "license": LICENSE,
        "keywords": generic.get("keywords", []),
        "skills": "./skills/",
        "mcpServers": "./.mcp.json",
        "interface": interface,
    })

    write_json(PLUGIN / ".mcp.json", {"mcpServers": {"seqera": {"type": "http", "url": MCP_URL}}})

    if not (PLUGIN / ICON).is_file():
        sys.exit(f"icon not found: {ICON}")

    skills = sorted(p.parent.name for p in (PLUGIN / "skills").glob("*/SKILL.md"))
    print(f"imported {name} {version}: {len(skills)} skills")


if __name__ == "__main__":
    main()
