"""Workspace command tests for iew-review."""

import os
import subprocess
import sys
import tempfile

import pytest


def test_iew_review_command_exists():
    """The iew-review command should be executable."""
    result = subprocess.run(
        [sys.executable, "-m", "iew-review", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "iew-review" in result.stdout or "iew-review" in result.stderr


def test_iew_review_no_file(capsys):
    """iew-review without arguments should error."""
    result = subprocess.run(
        [sys.executable, "-m", "iew-review"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Error" in result.stderr or "Usage" in result.stderr


def test_iew_review_with_file(capsys, tmp_path):
    """iew-review should review a given file."""
    f = tmp_path / "test.js"
    f.write_text("// TODO: fix me\n")

    result = subprocess.run(
        [sys.executable, "-m", "iew-review", str(f)],
        capture_output=True,
        text=True,
    )
    # The command runs iew on the file, so output should contain feedback
    assert result.returncode == 0 or "TODO" in result.stdout or "TODO" in result.stderr
    captured = capsys.readouterr()
    # At minimum, the file should have been processed
    assert "test.js" in captured.out or "test.js" in captured.stderr


def test_iew_review_relative_path(tmp_path, capsys):
    """iew-review should resolve relative paths."""
    f = tmp_path / "subdir" / "test.js"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("// TODO: fix me\n")

    result = subprocess.run(
        [sys.executable, "-m", "iew-review", "test.js"],
        capture_output=True,
        text=True,
        cwd=str(f.parent),
    )
    # Should work with relative path
    assert result.returncode == 0 or "TODO" in result.stdout or "TODO" in result.stderr
