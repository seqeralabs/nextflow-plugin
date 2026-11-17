"""Exercise the consolidation CLI against independent package fixtures."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).with_name("consolidate_skills.py")


class ConsolidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        files = {
            "skills/old/SKILL.md": "---\nname: old\ndescription: Original task\n---\n# Original task\n\nRead [details](references/details.md).\n",
            "skills/old/references/details.md": "Preserve scheduler semantics.\n",
            "skills/old/scripts/check.sh": "#!/bin/sh\nprintf 'checked\\n'\n",
            "skills/owner/SKILL.md": "---\nname: owner\ndescription: Current task\n---\n# Current task\n",
            "skills/caller/SKILL.md": "---\nname: caller\ndescription: Call old when needed\n---\nUse `old` for this task.\n",
        }
        entries = []
        for relative, text in files.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            entries.append({"path": relative, "source": f"upstream/{relative}",
                            "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
                            "bundled_sha256": hashlib.sha256(text.encode()).hexdigest(), "override": False})
        (self.root / "sources.json").write_text(json.dumps({"files": entries, "claude_curation": {"edited_files": []}}))
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps({"groups": [{"folds": [{"from": "old", "to": "owner", "heading": "Original task playbook", "when": "When doing the original task.", "label": "original task"}]}]}))

    def run_cli(self):
        return subprocess.run([sys.executable, "-I", str(CLI), "--root", str(self.root), "--sources", str(self.root / "sources.json"), "--plan", str(self.plan)], capture_output=True, text=True)

    def test_moves_assets_and_routes_callers_with_original_provenance(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / "skills/old").exists())
        guide = self.root / "skills/owner/references/old/README.md"
        self.assertEqual(guide.read_text(), "# Original task\n\nRead [details](references/details.md).\n")
        self.assertEqual((guide.parent / "references/details.md").read_text(), "Preserve scheduler semantics.\n")
        self.assertEqual((guide.parent / "scripts/check.sh").read_text(), "#!/bin/sh\nprintf 'checked\\n'\n")
        self.assertIn("[original task](references/old/README.md)", (self.root / "skills/owner/SKILL.md").read_text())
        caller = (self.root / "skills/caller/SKILL.md").read_text()
        self.assertIn("description: Call owner when needed", caller)
        self.assertIn("[original task](../owner/references/old/README.md)", caller)
        sources = json.loads((self.root / "sources.json").read_text())
        moved = next(entry for entry in sources["files"] if entry["path"] == "skills/owner/references/old/README.md")
        self.assertEqual(moved["source"], "upstream/skills/old/SKILL.md")
        for entry in sources["files"]:
            self.assertEqual(entry["bundled_sha256"], hashlib.sha256((self.root / entry["path"]).read_bytes()).hexdigest())

    def test_rebases_external_links_and_keeps_internal_asset_links(self):
        original = self.root / "skills/old/SKILL.md"
        original.write_text(original.read_text() + "\nRead [current task](../owner/SKILL.md#workflow).\n")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        guide = self.root / "skills/owner/references/old/README.md"
        self.assertIn("[current task](../../SKILL.md#workflow)", guide.read_text())
        self.assertIn("[details](references/details.md)", guide.read_text())
        self.assertTrue((guide.parent / "../../SKILL.md").resolve().is_file())

    def test_short_reference_replaces_guide_and_drops_mirrored_schema(self):
        (self.root / "connection.md").write_text("# Connection\n\nUse live tool schemas.\n")
        plan = json.loads(self.plan.read_text())
        fold = plan["groups"][0]["folds"][0]
        fold["guide_override"] = "connection.md"
        fold["drop"] = ["references/details.md"]
        self.plan.write_text(json.dumps(plan))
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        destination = self.root / "skills/owner/references/old"
        self.assertEqual((destination / "README.md").read_text(), "# Connection\n\nUse live tool schemas.\n")
        self.assertFalse((destination / "references/details.md").exists())
        sources = json.loads((self.root / "sources.json").read_text())
        self.assertNotIn("skills/owner/references/old/references/details.md", [entry["path"] for entry in sources["files"]])
        self.assertTrue((destination / "scripts/check.sh").is_file())

    def test_replaying_a_completed_plan_is_a_noop(self):
        self.assertEqual(self.run_cli().returncode, 0)
        before = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(self.run_cli().returncode, 0)
        after = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(after, before)

    def test_behavioral_edit_is_applied_and_replayable(self):
        plan = json.loads(self.plan.read_text())
        plan["post_edits"] = [{"path": "skills/owner/SKILL.md", "old": "# Current task", "new": "# Scoped task"}]
        self.plan.write_text(json.dumps(plan))
        self.assertEqual(self.run_cli().returncode, 0)
        self.assertIn("# Scoped task", (self.root / "skills/owner/SKILL.md").read_text())
        before = (self.root / "sources.json").read_bytes()
        self.assertEqual(self.run_cli().returncode, 0)
        self.assertEqual((self.root / "sources.json").read_bytes(), before)

    def test_missing_source_and_guide_fails_explicitly(self):
        import shutil
        shutil.rmtree(self.root / "skills/old")
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing source skill and consolidated guide: old", result.stderr)

    def test_upstream_edit_drift_fails_explicitly(self):
        plan = json.loads(self.plan.read_text())
        plan["groups"][0]["edits"] = [{"path": "skills/owner/SKILL.md", "old": "No longer in the upstream source", "new": "Replacement"}]
        self.plan.write_text(json.dumps(plan))
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must match exactly once", result.stderr)
        self.assertTrue((self.root / "skills/old/SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
