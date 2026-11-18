"""Replay directory-compatible overlays through a real import of a synthetic package."""

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("import_package", TOOLS / "import_package.py")
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


class ImportTests(unittest.TestCase):
    def test_reimport_restores_overlays_and_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, package = Path(tmp) / "repo", Path(tmp) / "package"
            shutil.copytree(TOOLS, repo / "tools")
            # Consolidation has its own integration suite; use an independent empty
            # plan here so this fixture exercises import without needing all skills.
            (repo / "tools/skill_consolidations.json").write_text('{"groups": []}')
            files = {"skills/unrelated/SKILL.md": "Keep this upstream content.\n",
                     "skills/nextflow-development/SKILL.md": "Run scripts/check_environment.py\n",
                     "skills/nextflow-development/references/geo-sra-acquisition.md": "Old acquisition instructions\n",
                     "skills/repair-workflow/SKILL.md": "Run the old Python linter\n",
                     "skills/nextflow-development/scripts/check_environment.py": "#!/usr/bin/python3\n",
                     "skills/nextflow-development/scripts/config/genomes.yaml": "genomes: {}\n",
                     "skills/nf-pipeline-design/scripts/nflint/cli.py": "old linter\n",
                     "assets/nextflow-uploaded-logo.png": "test icon",
                     "assets/nextflow.svg": "old SVG",
                     "licenses/test.txt": "test license"}
            for skill in importer.EXCLUDED_SKILLS:
                files[f"skills/{skill}/SKILL.md"] = "Excluded\n"
            for rel, old, _ in importer.EDITS:
                files[rel] = files.get(rel, "") + old + "\n"
            entries = []
            for rel, content in files.items():
                path = package / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                entries.append(dict(path=rel, source=f"upstream/{rel}",
                                    source_sha256=digest, bundled_sha256=digest, override=False))
            (package / "sources.json").write_text(json.dumps({"files": entries}))
            (package / "plugin.json").write_text(json.dumps(dict(name="nextflow", description="Fixture")))
            (package / ".codex-plugin").mkdir()
            (package / ".codex-plugin/plugin.json").write_text(json.dumps({"interface": {
                "displayName": "Nextflow", "shortDescription": "Fixture", "longDescription": "Fixture"}}))
            overlays = repo / "tools/curation/overlays"
            self.assertEqual(len(list(overlays.rglob("*.md"))), 9)
            for attempt in range(2):
                result = subprocess.run([sys.executable, "-I", str(repo / "tools/import_package.py"),
                                         str(package)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                plugin = repo / "plugins/nextflow"
                sources = json.loads((repo / "sources.json").read_text())
                by_path = {entry["path"]: entry for entry in sources["files"]}
                self.assertEqual(len(by_path), len(sources["files"]))
                for asset in overlays.rglob("*.md"):
                    rel = asset.relative_to(overlays).as_posix()
                    self.assertEqual((plugin / rel).read_bytes(), asset.read_bytes())
                    self.assertEqual(by_path[rel]["bundled_sha256"], hashlib.sha256(asset.read_bytes()).hexdigest())
                    self.assertTrue(by_path[rel]["override"])
                    if rel in files:
                        self.assertEqual(by_path[rel]["source"], f"upstream/{rel}")
                        self.assertEqual(by_path[rel]["source_sha256"], hashlib.sha256(files[rel].encode()).hexdigest())
                self.assertFalse((plugin / "skills/nextflow-development/scripts").exists())
                self.assertFalse((plugin / "skills/nf-pipeline-design/scripts").exists())
                self.assertEqual((plugin / "skills/nextflow-development/references/config/genomes.yaml").read_text(), "genomes: {}\n")
                self.assertEqual((plugin / "skills/unrelated/SKILL.md").read_text(), files["skills/unrelated/SKILL.md"])
                check = subprocess.run([sys.executable, "-I", str(repo / "tools/check_sources.py")], capture_output=True, text=True)
                self.assertEqual(check.returncode, 0, check.stdout + check.stderr)


if __name__ == "__main__":
    unittest.main()
