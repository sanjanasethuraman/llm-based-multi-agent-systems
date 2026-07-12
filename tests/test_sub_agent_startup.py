import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.agents.agent_mcp_server import open_startup_log


class SubAgentStartupTests(unittest.TestCase):
    def test_startup_log_uses_cross_platform_temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("backend.agents.agent_mcp_server.tempfile.gettempdir", return_value=tmpdir):
                handle = open_startup_log()
                try:
                    handle.write("started\n")
                    path = Path(handle.name)
                finally:
                    handle.close()

        self.assertEqual(path.name, "sub-agent-startup.log")
        self.assertEqual(path.parent.name, "visual-mas")


if __name__ == "__main__":
    unittest.main()
