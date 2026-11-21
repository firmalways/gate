import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from firmalways_gate.benchmark import generate, run

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def cli(*args, stdin=None):
    return subprocess.run(
        [sys.executable, "-m", "firmalways_gate", *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=ENV,
        timeout=60,
    )


class CliTest(unittest.TestCase):
    def test_scan_text(self):
        result = cli("scan", "นายสมชาย ใจดี โทร 0812345678")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "นาย«PERSON_1» โทร «PHONE_1»")
        self.assertIn("PHONE", result.stderr)

    def test_scan_stdin_json(self):
        result = cli("scan", "--json", stdin="บัตร 1101700203611")
        self.assertEqual(json.loads(result.stdout)["masked_text"], "บัตร «THAI_NATIONAL_ID_1»")

    def test_scan_blocked_exit_code(self):
        result = cli("scan", "key " + "AKIA" + "IOSFODNN7EXAMPLE")
        self.assertEqual(result.returncode, 1)
        self.assertIn("BLOCKED: SECRET", result.stderr)

    def test_policy_error_exit_code(self):
        result = cli("scan", "x", "--policy", "/nonexistent.toml")
        self.assertEqual(result.returncode, 2)

    def test_benchmark_command(self):
        result = cli("benchmark", "--repeats", "2")
        self.assertEqual(result.returncode, 0)
        self.assertIn("OVERALL", result.stdout)


class BenchmarkTest(unittest.TestCase):
    def test_generation_is_deterministic(self):
        self.assertEqual(generate(seed=1, repeats=2), generate(seed=1, repeats=2))

    def test_gold_spans_point_at_values(self):
        for sample in generate(seed=3, repeats=3):
            for _, start, end in sample.spans:
                self.assertTrue(sample.text[start:end].strip())

    def test_regression_thresholds(self):
        report = run(seed=11, repeats=20)
        self.assertGreaterEqual(report["overall"]["precision"], 0.95)
        self.assertGreaterEqual(report["overall"]["recall"], 0.95)
        self.assertGreaterEqual(report["protection_recall"], 0.98)
        self.assertEqual(report["negative_false_positives"], 0)


if __name__ == "__main__":
    unittest.main()
