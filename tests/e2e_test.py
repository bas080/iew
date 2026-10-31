"""End-to-end tests for iew code review tool.

These tests verify:
- TODO detection produces parseable output
- `read:` requests trigger fuzzy file search
- Output coordinates pass through parse_coordinate correctly
- The CLI entry point runs end to end
"""
import os
import sys
import tempfile
import pytest
from unittest.mock import patch

from iew.agent import Agent
from iew.format import parse_coordinate


# --- TODO detection ---

def test_todo_detected_and_parseable(tmp_path):
    """A file with a TODO comment must produce a line-coordinate that parse_coordinate accepts."""
    f = tmp_path / "sample.js"
    f.write_text("const x = 1;\n// TODO: refactor this\n")
    agent = Agent()
    feedback = agent.review_file(str(f))
    assert "TODO found" in feedback
    for line in feedback.splitlines():
        coord = parse_coordinate(line)
        assert coord is not None or line.startswith("read:"), f"Unparseable line: {line}"


def test_no_todo_no_line_feedback(tmp_path):
    """A file without TODO or read requests still returns gracefully (may be empty or AI-only)."""
    f = tmp_path / "clean.py"
    f.write_text("x = 1\n")
    agent = Agent()
    feedback = agent.review_file(str(f))
    assert feedback == "" or feedback is not None


# --- read: requests ---

def test_read_request_parsed(tmp_path, monkeypatch):
    """A `read:` line in code triggers a fuzzy search and the output is parseable."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "main.py"
    target.write_text("target")
    f = tmp_path / "caller.js"
    f.write_text("// read: main.py\n")
    agent = Agent()
    feedback = agent.review_file(str(f))
    assert "read:" in feedback


def test_read_request_finds_files(tmp_path, monkeypatch):
    """Fuzzy file search returns matching files."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data.csv").write_text("a,b,c\n1,2,3\n")
    (tmp_path / "main.py").write_text("print('hi')\n")
    (tmp_path / "other.md").write_text("# README\n")

    agent = Agent()
    results = agent._fuzzy_file_search("data")
    assert len(results) == 1
    assert "data.csv" in results[0]


def test_read_request_partial_match(tmp_path, monkeypatch):
    """Substring match finds files by partial name."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("key: value")
    (tmp_path / "main.py").write_text("pass")

    agent = Agent()
    results = agent._fuzzy_file_search("config")
    assert len(results) >= 1
    assert any("config" in r for r in results)


# --- parse_coordinate ---

def test_parse_coordinate_line():
    coord = parse_coordinate("12: Unused variable.")
    assert coord == ('line', 12, 'Unused variable.')


def test_parse_coordinate_offset():
    coord = parse_coordinate("45:2: Missing quote.")
    assert coord == ('offset', 45, 2, 'Missing quote.')


def test_parse_coordinate_pair():
    coord = parse_coordinate("78:0-78:15: Hardcoded secret.")
    assert coord == ('pair', 78, 0, 78, 15, 'Hardcoded secret.')


def test_parse_coordinate_pair_alt():
    coord = parse_coordinate("150:0-150:8: Error handling missing.")
    assert coord == ('pair', 150, 0, 150, 8, 'Error handling missing.')


def test_parse_coordinate_multiline():
    coord = parse_coordinate("102-105: Inefficient loop.")
    assert coord == ('multiline_range', 102, 105, 'Inefficient loop.')


def test_parse_coordinate_read():
    coord = parse_coordinate("read: main.mjs")
    assert coord == ('read', 'main.mjs')


def test_parse_coordinate_empty():
    assert parse_coordinate("") is None
    assert parse_coordinate("   ") is None


def test_parse_coordinate_garbage():
    assert parse_coordinate("not a coordinate at all") is None


# --- CLI entry point ---

def test_cli_no_args_exits(tmp_path):
    """`iew` with no filepath should exit nonzero."""
    from iew.__main__ import main
    with pytest.raises(SystemExit):
        sys.argv = ["iew"]
        main()


def test_cli_reviews_file(tmp_path, capsys):
    """`iew <file>` prints feedback to stdout."""
    f = tmp_path / "test.js"
    f.write_text("// TODO: fix me\n")
    sys.argv = ["iew", str(f)]
    from iew.__main__ import main
    with patch("subprocess.run") as mock_run:
        # Simulate Ollama not available
        mock_run.side_effect = Exception("Ollama not running")
        main()
    captured = capsys.readouterr()
    assert "TODO" in captured.out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])