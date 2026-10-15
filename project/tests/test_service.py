from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from pixel_workbench.guidance import STARTER
from pixel_workbench.integration import install_codex, install_claude, configurations
from pixel_workbench.model import PixelError
from pixel_workbench.service import DocumentService


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.service = DocumentService(workspace=self.root / "work", runtime=self.root / "runtime")

    def payload(self, **fields):
        return {"expected_revision": self.service.doc.revision, "expected_document_id": self.service.doc.id, **fields}

    def call(self, endpoint, **fields):
        if endpoint=="/export":
            fields.setdefault("draft",True)  # These tests cover transport/export mechanics; review gating has its own suite.
        return self.service.dispatch("POST", endpoint, payload=self.payload(**fields))[0]

    def draw(self):
        return self.call("/command", ops=[{"op": "pixel", "x": 2, "y": 2, "color": 22}])

    def test_dry_run_changes_no_artwork_revision_history_or_files(self):
        before = self.service.doc.to_dict()
        result = self.call("/validate", ops=STARTER)
        self.assertTrue(result["dry_run"])
        self.assertIn("preview_png", result)
        self.assertEqual(self.service.doc.to_dict(), before)
        self.assertFalse(self.service.doc.undo_stack)
        self.assertFalse((self.root / "runtime" / "autosave.pixloom").exists())

    def test_unsaved_replacement_requires_explicit_intent(self):
        self.draw()
        old_id = self.service.doc.id
        with self.assertRaises(PixelError) as error:
            self.call("/new", width=16, height=16)
        self.assertEqual(error.exception.code, "UNSAVED_CHANGES")
        self.assertEqual(self.service.doc.id, old_id)
        self.call("/save", path="projects/original.pixloom")
        self.call("/new", width=16, height=16)
        self.assertNotEqual(self.service.doc.id, old_id)
        self.assertTrue((self.service.runtime / "recovery" / f"{old_id}.pixloom").exists())

    def test_save_undo_dirty_state_tracks_content_not_revision(self):
        self.call("/save", path="projects/a.pixloom")
        self.draw()
        self.assertTrue(self.service.dirty)
        self.call("/undo")
        self.assertFalse(self.service.dirty)

    def test_exact_request_retry_is_not_applied_twice(self):
        payload = self.payload(ops=[{"op": "frame_add"}], request_id="retry-1")
        first = self.service.dispatch("POST", "/command", payload=payload)[0]
        second = self.service.dispatch("POST", "/command", payload=payload)[0]
        self.assertTrue(second["replayed"])
        self.assertEqual(first["revision"], second["revision"])
        self.assertEqual(len(self.service.doc.durations), 2)
        changed = deepcopy(payload)
        changed["ops"] = [{"op": "clear"}]
        with self.assertRaises(PixelError) as error:
            self.service.dispatch("POST", "/command", payload=changed)
        self.assertEqual(error.exception.code, "REQUEST_ID_REUSED")

    def test_stale_plan_is_rejected(self):
        plan = self.payload(ops=[{"op": "clear"}])
        self.draw()
        with self.assertRaises(PixelError) as error:
            self.service.dispatch("POST", "/command", payload=plan)
        self.assertEqual(error.exception.code, "REVISION_CONFLICT")

    def test_export_layer_filter_does_not_change_visibility_or_dirty_state(self):
        self.call("/command", ops=[{"op": "rect", "x": 0, "y": 0, "width": 48, "height": 48, "color": 1},
                                   {"op": "layer_add", "id": "sprite", "name": "sprite"},
                                   {"op": "pixel", "x": 2, "y": 2, "color": 22}])
        before = self.service.doc.fingerprint()
        result = self.call("/export", path="exports/character.png", layers=["sprite"])
        with Image.open(result["path"]) as image:
            self.assertEqual(image.getpixel((0, 0))[3], 0)
            self.assertEqual(image.getpixel((2, 2))[3], 255)
        self.assertEqual(self.service.doc.fingerprint(), before)
        self.assertTrue(all(layer.visible for layer in self.service.doc.layers))

    def test_export_collision_preserves_existing_file(self):
        result = self.call("/export", path="exports/a.png")
        before = Path(result["path"]).read_bytes()
        self.draw()
        with self.assertRaises(PixelError) as error:
            self.call("/export", path="exports/a.png")
        self.assertEqual(error.exception.code, "FILE_EXISTS")
        self.assertEqual(Path(result["path"]).read_bytes(), before)
        self.call("/export", path="exports/a.png", overwrite=True)

    def test_png_import_invalid_size_keeps_existing_document(self):
        source = self.root / "too-big.png"
        Image.new("RGBA", (513, 1)).save(source)
        old = self.service.doc.id
        with self.assertRaises(PixelError):
            self.call("/import", path=str(source))
        self.assertEqual(self.service.doc.id, old)

    def test_busy_human_stroke_rejects_external_edit(self):
        self.service.view["gesture_active"] = True
        with self.assertRaises(PixelError) as error:
            self.draw()
        self.assertEqual(error.exception.code, "EDITOR_BUSY")

    def test_client_config_installation_preserves_other_servers_and_settings(self):
        codex = self.root / "config.toml"
        codex.write_text('[mcp_servers.other]\ncommand="node"\nargs=["--yes", "server"]\n\n[features]\nsome_flag=true\n', encoding="utf-8")
        before = codex.read_text()
        result = install_codex(codex)
        self.assertEqual(Path(result["backup"]).read_text(), before)
        import tomllib
        data = tomllib.loads(codex.read_text())
        self.assertEqual(data["mcp_servers"]["other"]["args"], ["--yes", "server"])
        self.assertTrue(data["features"]["some_flag"])
        self.assertEqual(install_codex(codex)["status"], "already_configured")
        claude = self.root / "claude.json"
        claude.write_text(json.dumps({"preferences": {"font": "large"}, "mcpServers": {"other": {"command": "node"}}}))
        install_claude(claude)
        data = json.loads(claude.read_text())
        self.assertEqual(data["mcpServers"]["other"], {"command": "node"})
        self.assertEqual(data["preferences"], {"font": "large"})

    def test_gui_configuration_uses_console_python_for_mcp(self):
        config = configurations(executable=self.root / "pythonw.exe")
        self.assertEqual(Path(config["entry"]["command"]).name, "python.exe")
        self.assertIn("--mcp", config["entry"]["args"])

    def test_configuration_preserves_virtualenv_interpreter_symlink(self):
        import sys
        link = self.root / "venv-python"
        try:
            link.symlink_to(sys.executable)
        except OSError:
            self.skipTest("This platform/user cannot create symbolic links")
        config = configurations(executable=link)
        self.assertEqual(config["entry"]["command"], str(link.absolute()))


if __name__ == "__main__":
    unittest.main()
