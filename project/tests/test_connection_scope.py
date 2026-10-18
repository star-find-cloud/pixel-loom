"""Generated host configurations must reconnect to the editor's actual isolated paths."""
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from pixel_workbench.integration import configurations


class ConnectionScopeTests(unittest.TestCase):
    def test_both_host_formats_preserve_data_and_workspace_with_spaces(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder)/'separate data';work=Path(folder)/'作品 workspace'
            with patch('pixel_workbench.paths.DATA_HOME',home),patch('pixel_workbench.paths.WORKSPACE',work):
                config=configurations(executable=Path(folder)/'python.exe')
            args=config['entry']['args']
            self.assertEqual(args[args.index('--data-dir')+1],str(home))
            self.assertEqual(args[args.index('--workspace')+1],str(work))
            self.assertEqual(tomllib.loads(config['codex'])['mcp_servers']['pixel_loom']['args'],args)
            self.assertEqual(json.loads(json.dumps(config['claude']))['mcpServers']['pixel-loom']['args'],args)

    def test_frozen_host_uses_sibling_console_and_keeps_scope_with_headless(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);gui=root/'PixelLoom.exe';console=root/'PixelLoomMCP.exe';console.touch()
            with patch('pixel_workbench.integration.sys.frozen',True,create=True),\
                 patch('pixel_workbench.paths.DATA_HOME',root/'data'),patch('pixel_workbench.paths.WORKSPACE',root/'work'):
                config=configurations(executable=gui,headless=True)
            self.assertEqual(config['entry']['command'],str(console))
            self.assertEqual(config['entry']['args'][0],'--mcp')
            self.assertIn('--headless',config['entry']['args']);self.assertIn('--data-dir',config['entry']['args'])


if __name__=='__main__':unittest.main()
