#!/usr/bin/env python3
"""pytest bridge for the aggregating self-check runners in this directory.

The runners keep their direct-entry behavior: they collect every failed check and
print one aggregate report. pytest cannot inspect that report inside the same
process, so each test here runs one runner as a subprocess and asserts on its
exit code, carrying the runner's stdout into pytest's failure output.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run_script(filename):
    cmd = [sys.executable, os.path.join(HERE, filename)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=HERE)
    assert proc.returncode == 0, (
        "%s exited %d\ncommand: %s\n--- stdout ---\n%s\n--- stderr ---\n%s"
        % (filename, proc.returncode, " ".join(cmd), proc.stdout, proc.stderr)
    )


def test_wheel_registry_runner():
    run_script("test_wheel_registry.py")


def test_skill_runner():
    run_script("test_skill.py")


def test_wheel_community_runner():
    run_script("test_wheel_community.py")
