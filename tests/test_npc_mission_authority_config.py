import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("authority_config", Path(__file__).parents[1] / "tools/configure-npc-mission-authority.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AuthorityConfigurationTests(unittest.TestCase):
    def test_private_configuration_replays_and_preserves_existing_assignments(self):
        with tempfile.TemporaryDirectory() as directory:
            gateway = Path(directory) / "gateway.env"
            coordinator = Path(directory) / "coordinator.env"
            gateway.write_text("EXISTING='literal value'\n")
            coordinator.write_text("OTHER=value\n")
            gateway.chmod(0o600)
            coordinator.chmod(0o600)
            module.configure(gateway, coordinator, "https://localhost:38443/")
            before = (gateway.read_bytes(), coordinator.read_bytes())
            module.configure(gateway, coordinator, "https://localhost:38443/")
            self.assertEqual(before, (gateway.read_bytes(), coordinator.read_bytes()))
            self.assertIn("EXISTING='literal value'", gateway.read_text())
            self.assertEqual(0o600, gateway.stat().st_mode & 0o777)
            self.assertEqual(0o600, coordinator.stat().st_mode & 0o777)
            self.assertEqual(module.read_private_env(gateway)[1][module.GATEWAY_KEY],
                             module.read_private_env(coordinator)[1][module.COORDINATOR_KEY])

    def test_insecure_or_shared_files_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared.env"
            path.write_text("EXISTING=value\n")
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                module.read_private_env(path)
            path.chmod(0o600)
            with self.assertRaises(ValueError):
                module.configure(path, path, "https://localhost/")

    def test_https_origin_required(self):
        for url in ("http://localhost/", "https://user:secret@localhost/", "https://localhost/path", "https://localhost/?q=1"):
            with self.assertRaises(ValueError):
                module.configure(Path("missing-gateway"), Path("missing-coordinator"), url)

    def test_existing_mismatched_keys_are_not_rotated(self):
        with tempfile.TemporaryDirectory() as directory:
            gateway, coordinator = (Path(directory) / name for name in ("g.env", "c.env"))
            gateway.write_text(f"{module.GATEWAY_KEY}={'x' * 32}\n")
            coordinator.write_text(f"{module.COORDINATOR_KEY}={'y' * 32}\n")
            gateway.chmod(0o600)
            coordinator.chmod(0o600)
            before = gateway.read_bytes(), coordinator.read_bytes()
            with self.assertRaises(ValueError):
                module.configure(gateway, coordinator, "https://localhost/")
            self.assertEqual(before, (gateway.read_bytes(), coordinator.read_bytes()))
