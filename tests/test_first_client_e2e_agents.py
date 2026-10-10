import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
PREPARER = REPOSITORY / "bin/prepare-first-client-e2e-agents.py"


class FirstClientE2eAgentConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="first-client-e2e-agent-test-")
        self.run_root = Path(self.temporary.name)
        (self.run_root / "gameserver").mkdir()
        (self.run_root / "coordinator.env").write_text(
            "export ASPNETCORE_URLS=https://localhost:38444\n"
            "export Coordinator__InternalApiKey=test-api-key\n"
            "export Coordinator__StateFile=/tmp/coordinator-state.json\n"
        )
        (self.run_root / "gameserver/li01.env").write_text(
            "export LANCER_NEXUS_GAME_INSTANCE_KEY=test-instance-key-li01\n"
        )
        (self.run_root / "gameserver/li02.env").write_text(
            "export LANCER_NEXUS_GAME_INSTANCE_KEY=test-instance-key-li02\n"
        )
        self.configs = {}
        for suffix, instance, system, endpoint, port in (
            ("li01", "li01", "li01", "127.0.0.2:25443", 25443),
            ("li02", "li02", "li03", "127.0.0.3:25444", 25444),
        ):
            config = {
                "InstanceId": instance,
                "SystemId": system,
                "InstanceEndpoint": endpoint,
                "MaxPlayers": 8,
                "Port": port,
            }
            self.configs[suffix] = config
            (self.run_root / f"gameserver/llserver-{suffix}.json").write_text(json.dumps(config))

    def tearDown(self):
        self.temporary.cleanup()

    def run_preparer(self):
        return subprocess.run(
            [sys.executable, str(PREPARER), "--run-dir", str(self.run_root)],
            capture_output=True,
            text=True,
        )

    def test_provisions_two_agent_identities_and_flhook_transport(self):
        result = self.run_preparer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("test-api-key", result.stdout + result.stderr)

        private = self.run_root / "agent-control"
        coordinator = dict(line.removeprefix("export ").split("=", 1)
                           for line in (self.run_root / "coordinator.env").read_text().splitlines())
        self.assertEqual(coordinator["Coordinator__Quic__Enabled"], "true")
        self.assertEqual(coordinator["Coordinator__Quic__Port"], "27443")
        self.assertTrue(Path(coordinator["Coordinator__Quic__ServerCertificatePath"]).is_file())
        coordinator_ca = coordinator["Coordinator__Quic__ClientCaCertificatePath"]
        self.assertTrue(Path(coordinator_ca).is_file())

        for suffix, instance, system in (("li01", "li01", "li01"), ("li02", "li02", "li03")):
            config_path = self.run_root / f"gameserver/llserver-{suffix}.json"
            config = json.loads(config_path.read_text())
            self.assertEqual((config["InstanceId"], config["SystemId"]), (instance, system))
            self.assertTrue(config["FlHookCompatEnabled"])
            self.assertTrue(config["FlHookCompatClusterEventsEnabled"])
            self.assertEqual(config["ClusterAgentNodeId"], f"first-e2e-{suffix}")
            self.assertTrue(Path(config["CoordinatorQuicClientCertificate"]).is_file())
            self.assertEqual(config["CoordinatorQuicCaCertificate"], coordinator_ca)
            self.assertTrue(Path(config["FlHookCompatEventOutboxFile"]).parent.is_dir())

            agent_env = private / f"{suffix}-agent.env"
            agent_values = dict(line.removeprefix("export ").split("=", 1)
                                for line in agent_env.read_text().splitlines())
            self.assertEqual(agent_values["Agent__AgentId"], f"first-e2e-agent-{suffix}")
            self.assertEqual(agent_values["Agent__Instance__SystemId"], system)
            self.assertEqual(agent_values["Agent__Capabilities__3"], "flhook_events_v1")
            self.assertEqual(agent_values["Agent__Coordinator__CaCertificatePath"], coordinator_ca)
            self.assertEqual(agent_values["Agent__Coordinator__ServerName"], "localhost")
            self.assertEqual(config["CoordinatorQuicServerName"], "localhost")
            self.assertNotEqual(agent_values["Agent__StateFile"],
                                (private / f"{('li02' if suffix == 'li01' else 'li01')}-heartbeat-sequence.txt").as_posix())
            self.assertEqual(agent_env.stat().st_mode & 0o777, 0o600)

        self.assertEqual(private.stat().st_mode & 0o777, 0o700)
        self.assertEqual((private / "control-ca.key").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.run_root / "coordinator.env").stat().st_mode & 0o777, 0o600)

    def test_refuses_wrong_target_system(self):
        config_path = self.run_root / "gameserver/llserver-li02.json"
        config = json.loads(config_path.read_text())
        config["SystemId"] = "li01"
        config_path.write_text(json.dumps(config))
        original_coordinator_env = (self.run_root / "coordinator.env").read_bytes()
        result = self.run_preparer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("li02 LLServer config must identify li02/li03", result.stderr)
        self.assertEqual((self.run_root / "coordinator.env").read_bytes(), original_coordinator_env)
        self.assertFalse((self.run_root / "agent-control").exists())

    def test_repeated_preparation_preserves_certificate_identity(self):
        first = self.run_preparer()
        self.assertEqual(first.returncode, 0, first.stderr)
        pfx = self.run_root / "agent-control/li02-agent.pfx"
        certificate = self.run_root / "agent-control/li02-agent.crt"
        first_digests = tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in (pfx, certificate))

        second = self.run_preparer()
        self.assertEqual(second.returncode, 0, second.stderr)
        second_digests = tuple(hashlib.sha256(path.read_bytes()).hexdigest() for path in (pfx, certificate))
        self.assertEqual(second_digests, first_digests)

    def test_refuses_group_or_world_accessible_run_directory(self):
        self.run_root.chmod(0o755)
        result = self.run_preparer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Run directory must not be accessible", result.stderr)


if __name__ == "__main__":
    unittest.main()
