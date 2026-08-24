import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "packaging" / "windows" / "write_build_manifest.py"
SPEC = importlib.util.spec_from_file_location("write_build_manifest", MODULE_PATH)
manifest_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(manifest_module)


class WindowsPackagingTests(unittest.TestCase):
    def test_manifest_is_deterministic_and_sorted(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "secure-messaging-helper.exe").write_bytes(b"helper")
            internal = bundle / "_internal"
            internal.mkdir()
            (internal / "z.dll").write_bytes(b"z")
            (internal / "a.dll").write_bytes(b"a")
            packages = [
                {"name": "vodozemac", "version": "x"},
                {"name": "matrix-nio", "version": "0.26.0"},
            ]
            first = manifest_module.build_manifest(bundle, "abc123", False, "3.11.x", "6.22.2", packages)
            second = manifest_module.build_manifest(bundle, "abc123", False, "3.11.x", "6.22.2", list(reversed(packages)))
            self.assertEqual(first, second)
            self.assertEqual(
                ["secure-messaging-helper.exe", "_internal/a.dll", "_internal/z.dll"],
                [entry["path"] for entry in first["files"]],
            )

    def test_manifest_excludes_itself(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "secure-messaging-helper.exe").write_bytes(b"helper")
            (bundle / "build-manifest.json").write_text("old", encoding="utf-8")
            result = manifest_module.build_manifest(bundle, "abc123", False, "3.11.x", "6.22.2", [])
            self.assertNotIn("build-manifest.json", [entry["path"] for entry in result["files"]])

    def test_manifest_requires_helper_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "helper"):
                manifest_module.build_manifest(Path(directory), "abc123", False, "3.11.x", "6.22.2", [])

    def test_package_inventory_is_name_version_only(self):
        normalized = manifest_module.normalize_packages([
            {"name": "B", "version": "2", "location": "C:/secret/path"},
            {"name": "a", "version": "1"},
        ])
        self.assertEqual([{"name": "a", "version": "1"}, {"name": "B", "version": "2"}], normalized)
        self.assertNotIn("location", json.dumps(normalized))

    def test_spec_is_onedir_console_and_collects_e2e_backend(self):
        text = (ROOT / "packaging" / "windows" / "secure-messaging-helper.spec").read_text(encoding="utf-8")
        self.assertIn('for package in ("nio", "vodozemac")', text)
        self.assertIn("COLLECT(", text)
        self.assertIn("console=True", text)
        self.assertNotIn("onefile", text.lower().replace("onefile rather than", ""))

    def test_build_requirements_pin_top_level_packaging_inputs(self):
        requirements = (ROOT / "packaging" / "windows" / "build-requirements.txt").read_text(encoding="utf-8")
        self.assertIn("matrix-nio[e2e]==0.26.0", requirements)
        self.assertIn("pyinstaller==6.22.2", requirements)
        self.assertNotIn(">=", requirements)

    def test_build_driver_is_fail_closed_and_runs_both_smokes(self):
        script = (ROOT / "packaging" / "windows" / "Build-WindowsHelper.ps1").read_text(encoding="utf-8")
        for expected in (
            "Working tree is dirty",
            "-FilePath 'py' -Arguments @('-3.11'",
            "Matrix E2EE imports: PASS",
            "'unittest', 'discover'",
            "SECURE_MESSAGING_TEST_TRANSPORT = 'memory'",
            "SECURE_MESSAGING_HELPER_PATH",
            "SecureMessaging.Conformance.csproj",
            "build-manifest.json",
            "Get-FileHash -Algorithm SHA256",
            "System.Text.UTF8Encoding($false)",
            "$Response.request_id -ne $RequestId",
        ):
            self.assertIn(expected, script)
        for forbidden in (
            "--specpath",
            "SECURE_MESSAGING_MATRIX_ACCESS_TOKEN =",
            "SECURE_MESSAGING_MATRIX_PICKLE_KEY =",
            "Invoke-WebRequest",
            "curl ",
        ):
            self.assertNotIn(forbidden, script)

    def test_dotnet_client_bounds_and_times_out_helper_process(self):
        client = (ROOT / "src-dotnet" / "SecureMessaging.Client" / "StdioSecureMessagingClient.cs").read_text(encoding="utf-8")
        self.assertIn("MaxResponseChars = 64 * 1024", client)
        self.assertIn("DefaultHelperTimeout = TimeSpan.FromSeconds(30)", client)
        self.assertIn("Path.IsPathFullyQualified", client)
        self.assertIn("process.Kill(entireProcessTree: true)", client)
        self.assertIn('"helper_timeout"', client)
        self.assertIn('"helper_response_too_large"', client)
        self.assertIn('"helper_response_mismatch"', client)
        self.assertIn("DrainAsync(process.StandardError", client)

    def test_dotnet_conformance_launches_packaged_helper_when_requested(self):
        program = (ROOT / "tests-dotnet" / "SecureMessaging.Conformance" / "Program.cs").read_text(encoding="utf-8")
        self.assertIn("SECURE_MESSAGING_HELPER_PATH", program)
        self.assertIn("SECURE_MESSAGING_TEST_TRANSPORT", program)
        self.assertIn("await client.SendAsync(smokeEnvelope)", program)
        self.assertIn("packaged-helper conformance: PASS", program)


if __name__ == "__main__":
    unittest.main()
