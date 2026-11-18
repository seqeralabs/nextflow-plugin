#!/usr/bin/env python3
"""Fold skill entrypoints into linked playbooks without losing assets or provenance.

Run after import_package.py's upstream edits. The checked-in consolidation plan
is replayed on every import; existing consolidated trees can also be updated.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

PLAN = Path(__file__).with_name("skill_consolidations.json")


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def split_frontmatter(text: str) -> tuple[str, str]:
    match = re.match(r"\A---\n.*?\n---\n", text, re.S)
    if not match:
        raise ValueError("skill must start with closed YAML frontmatter")
    return match.group(), text[match.end():]


def rebase_markdown_links(text: str, old_path: Path, new_path: Path,
                          source: Path, destination: Path) -> str:
    def relocate(match: re.Match) -> str:
        target = match.group(2)
        location, separator, anchor = target.partition("#")
        if not location or location.startswith(("/", "<")) or re.match(r"[a-zA-Z][\w+.-]*:", location):
            return match.group()
        resolved = (old_path.parent / location).resolve()
        if resolved.is_relative_to(source.resolve()):
            relative = resolved.relative_to(source.resolve())
            if relative == Path("SKILL.md"):
                relative = Path("README.md")
            resolved = destination / relative
        rebased = Path(os.path.relpath(resolved, new_path.parent)).as_posix()
        return f"{match.group(1)}{rebased}{separator}{anchor})"

    return re.sub(r"(\[[^\]]*\]\()([^\s)]+)\)", relocate, text)


def apply_consolidations(root: Path, plan: dict, assets: Path, sources_path: Path) -> None:
    sources = json.loads(sources_path.read_text())
    entries = {entry["path"]: entry for entry in sources["files"]}
    edited = set(sources["claude_curation"]["edited_files"])
    for group in plan["groups"]:
        folds = group["folds"]
        pending = [fold for fold in folds if (root / "skills" / fold["from"]).is_dir()]
        if pending and len(pending) != len(folds):
            raise ValueError("partially consolidated group; restore its source skills before replay")
        if not pending:
            for fold in folds:
                guide = root / "skills" / fold["to"] / "references" / fold["from"] / "README.md"
                if not guide.is_file():
                    raise ValueError(f"missing source skill and consolidated guide: {fold['from']}")
            continue

        # Exact, fail-closed adaptations precede moving/relinking this group.
        for edit in group.get("edits", []):
            path = root / edit["path"]
            text = path.read_text()
            if text.count(edit["old"]) != 1:
                raise ValueError(f"edit for {edit['path']} must match exactly once")
            path.write_text(text.replace(edit["old"], edit["new"]))

        for fold in folds:
            source = root / "skills" / fold["from"]
            receiver = root / "skills" / fold["to"] / "SKILL.md"
            destination = receiver.parent / "references" / fold["from"]
            if not receiver.is_file() or destination.exists():
                raise ValueError(f"invalid consolidation destination: {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), destination)
            old_guide = destination / "SKILL.md"
            _, body = split_frontmatter(old_guide.read_text())
            guide = destination / "README.md"
            guide.write_text(body.lstrip())
            old_guide.unlink()
            if fold.get("guide_override"):
                guide.write_text((assets / fold["guide_override"]).read_text())
            for dropped in fold.get("drop", []):
                (destination / dropped).unlink()
            for path in destination.rglob("*.md"):
                if path == guide and fold.get("guide_override"):
                    continue  # Authored override links already use the new location.
                relative = Path("SKILL.md") if path == guide else path.relative_to(destination)
                path.write_text(rebase_markdown_links(
                    path.read_text(), source / relative, path, source, destination,
                ))

            # Keep original source identity/hash; record new bundled path/hash below.
            prefix = f"skills/{fold['from']}/"
            for key in list(entries):
                if not key.startswith(prefix):
                    continue
                entry = entries.pop(key)
                relative = key[len(prefix):]
                if relative in fold.get("drop", []):
                    continue
                if relative == "SKILL.md":
                    relative = "README.md"
                entry["path"] = f"skills/{fold['to']}/references/{fold['from']}/{relative}"
                entry["override"] = True
                entries[entry["path"]] = entry
                edited.discard(key)
                edited.add(entry["path"])

            relative_guide = f"references/{fold['from']}/README.md"
            text = receiver.read_text().rstrip()
            text += f"\n\n## {fold['heading']}\n\n{fold['when']} Read [{fold['label']}]({relative_guide}) before proceeding.\n"
            receiver.write_text(text)

        # References replace invocation of removed skills. Frontmatter routes to
        # the surviving skill; bodies link directly to the appropriate playbook.
        for path in sorted((root / "skills").rglob("*.md")):
            text = path.read_text()
            frontmatter, body = split_frontmatter(text) if path.name == "SKILL.md" else ("", text)
            for fold in folds:
                old = fold["from"]
                guide = root / "skills" / fold["to"] / "references" / old / "README.md"
                relative = Path(os.path.relpath(guide, path.parent)).as_posix()
                pattern = rf"`{re.escape(old)}`|(?<![\w/-]){re.escape(old)}(?![\w/-]|\.md\b)"
                frontmatter = re.sub(pattern, fold["to"], frontmatter)
                # Do not change Markdown link destinations or the current guide's
                # self-references into self-invocation. Skill slugs are standalone tokens.
                body = re.sub(pattern, lambda _: f"[{fold['label']}]({relative})", body)
            path.write_text(frontmatter + body)

    # Behavioral adaptations run after all references have been relocated.
    for edit in plan.get("post_edits", []):
        path = root / edit["path"]
        text = path.read_text()
        if text.count(edit["old"]) == 1:
            path.write_text(text.replace(edit["old"], edit["new"]))
        elif text.count(edit["old"]) != 0 or text.count(edit["new"]) != 1:
            raise ValueError(f"post-edit for {edit['path']} must match exactly once")

    for entry in entries.values():
        path = root / entry["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["bundled_sha256"]:
            entry["override"] = True
            edited.add(entry["path"])
        entry["bundled_sha256"] = digest
    sources["files"] = list(entries.values())
    sources["claude_curation"]["consolidated_skills"] = [
        {"from": fold["from"], "to": fold["to"]}
        for group in plan["groups"] for fold in group["folds"]
    ]
    sources["claude_curation"]["edited_files"] = sorted(edited & entries.keys())
    write_json(sources_path, sources)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    repo = Path(__file__).resolve().parent.parent
    parser.add_argument("--root", type=Path, default=repo / "plugins" / "nextflow", help="plugin directory holding skills/")
    parser.add_argument("--sources", type=Path, default=repo / "sources.json", help="provenance file; paths are relative to --root")
    parser.add_argument("--plan", type=Path, default=PLAN)
    args = parser.parse_args()
    apply_consolidations(args.root.resolve(), json.loads(args.plan.read_text()), args.plan.parent, args.sources.resolve())


if __name__ == "__main__":
    main()
