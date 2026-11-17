#!/usr/bin/env python3
"""
Private fixture tests for execstart_stable_compare.

BEFORE (fail): pre-fix validate_models would reject post-daemon-reload ExecStart
AFTER (pass): post-fix stable-field comparison accepts post-reload ExecStart
              while still rejecting actual command identity changes.

Run: /home/ron/Projects/Hyprneuro/python/.venv/bin/python -I -m pytest tests/test_execstart_stable.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from execstart_stable_compare import (
    ExecStartStable,
    compare_execstart_stable,
    parse_execstart_stable,
    execstart_stable_fields,
)


# --- Realistic fixtures from actual 04 model snapshot ---

# Pre-daemon-reload (what the snapshot captured):
PRE_RELOAD_TEXT = (
    "{ path=/home/ron/.bin/lfm ; argv[]=/home/ron/.bin/lfm serve text ; "
    "ignore_errors=no ; start_time=[Sun 2026-11-15 20:25:30 EST] ; "
    "stop_time=[n/a] ; pid=115653 ; code=(null) ; status=0/0 }"
)

# Post-daemon-reload (what systemctl shows after reload, same process running):
POST_RELOAD_TEXT = (
    "{ path=/home/ron/.bin/lfm ; argv[]=/home/ron/.bin/lfm serve text ; "
    "ignore_errors=no ; start_time=[n/a] ; "
    "stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
)

PRE_RELOAD_OMNI = (
    "{ path=/home/ron/.bin/lfm ; argv[]=/home/ron/.bin/lfm serve omni ; "
    "ignore_errors=no ; start_time=[Sun 2026-11-15 20:25:30 EST] ; "
    "stop_time=[n/a] ; pid=115655 ; code=(null) ; status=0/0 }"
)

POST_RELOAD_OMNI = (
    "{ path=/home/ron/.bin/lfm ; argv[]=/home/ron/.bin/lfm serve omni ; "
    "ignore_errors=no ; start_time=[n/a] ; "
    "stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
)

PRE_RELOAD_DECISION = (
    "{ path=/home/ron/.bin/lfm ; argv[]=/home/ron/.bin/lfm serve decision ; "
    "ignore_errors=no ; start_time=[Sun 2026-11-15 20:25:30 EST] ; "
    "stop_time=[n/a] ; pid=115658 ; code=(null) ; status=0/0 }"
)

POST_RELOAD_DECISION = (
    "{ path=/home/ron/.bin/lfm ; argv[]=/home/ron/.bin/lfm serve decision ; "
    "ignore_errors=no ; start_time=[n/a] ; "
    "stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
)


# --- Tests: BEFORE (old full-string comparison would FAIL) ---

class TestBeforeFullStringComparison:
    """Demonstrate that naive full-string comparison fails post-reload."""

    def test_text_full_string_mismatch(self):
        assert PRE_RELOAD_TEXT != POST_RELOAD_TEXT

    def test_omni_full_string_mismatch(self):
        assert PRE_RELOAD_OMNI != POST_RELOAD_OMNI

    def test_decision_full_string_mismatch(self):
        assert PRE_RELOAD_DECISION != POST_RELOAD_DECISION


# --- Tests: AFTER (stable-field comparison PASSES) ---

class TestAfterStableFieldComparison:
    """Stable-field comparison accepts post-reload ExecStart (same command)."""

    def test_text_stable_match(self):
        compare_execstart_stable(PRE_RELOAD_TEXT, POST_RELOAD_TEXT)  # no raise

    def test_omni_stable_match(self):
        compare_execstart_stable(PRE_RELOAD_OMNI, POST_RELOAD_OMNI)  # no raise

    def test_decision_stable_match(self):
        compare_execstart_stable(PRE_RELOAD_DECISION, POST_RELOAD_DECISION)  # no raise

    def test_identical_strings_match(self):
        compare_execstart_stable(PRE_RELOAD_TEXT, PRE_RELOAD_TEXT)  # no raise


# --- Tests: Rejection (stable field changes MUST fail) ---

class TestRejection:
    """Actual command identity changes must be rejected."""

    def test_path_change_rejected(self):
        changed = (
            "{ path=/home/ron/.bin/lfm-UPDATED ; argv[]=/home/ron/.bin/lfm serve text ; "
            "ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        )
        with pytest.raises(ValueError, match="path drift"):
            compare_execstart_stable(PRE_RELOAD_TEXT, changed)

    def test_argv_change_rejected(self):
        changed = (
            "{ path=/home/ron/.bin/lfm ; argv[]=/home/ron/.bin/lfm serve text --extra-flag ; "
            "ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        )
        with pytest.raises(ValueError, match="argv drift"):
            compare_execstart_stable(PRE_RELOAD_TEXT, changed)

    def test_ignore_errors_change_rejected(self):
        changed = (
            "{ path=/home/ron/.bin/lfm ; argv[]=/home/ron/.bin/lfm serve text ; "
            "ignore_errors=yes ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        )
        with pytest.raises(ValueError, match="ignore_errors drift"):
            compare_execstart_stable(PRE_RELOAD_TEXT, changed)


# --- Tests: Malformed input rejection ---

class TestMalformedRejection:

    def test_missing_braces(self):
        with pytest.raises(ValueError, match="missing braces"):
            parse_execstart_stable("path=/foo ; argv[]=/foo")

    def test_missing_path(self):
        raw = "{ argv[]=/foo ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        with pytest.raises(ValueError, match="missing path"):
            parse_execstart_stable(raw)

    def test_missing_argv(self):
        raw = "{ path=/foo ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        with pytest.raises(ValueError, match="missing argv"):
            parse_execstart_stable(raw)

    def test_missing_ignore_errors(self):
        raw = "{ path=/foo ; argv[]=/foo bar ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        with pytest.raises(ValueError, match="missing ignore_errors"):
            parse_execstart_stable(raw)

    def test_empty_path(self):
        raw = "{ path= ; argv[]=/foo ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        with pytest.raises(ValueError, match="empty path"):
            parse_execstart_stable(raw)

    def test_empty_argv(self):
        raw = "{ path=/foo ; argv[]= ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        with pytest.raises(ValueError, match="empty argv"):
            parse_execstart_stable(raw)

    def test_invalid_ignore_errors_value(self):
        raw = "{ path=/foo ; argv[]=/foo ; ignore_errors=maybe ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        with pytest.raises(ValueError, match="invalid ignore_errors"):
            parse_execstart_stable(raw)

    def test_duplicate_path(self):
        raw = "{ path=/foo ; path=/bar ; argv[]=/foo ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        with pytest.raises(ValueError, match="duplicate path"):
            parse_execstart_stable(raw)

    def test_empty_string(self):
        with pytest.raises(ValueError):
            parse_execstart_stable("")

    def test_garbage(self):
        with pytest.raises(ValueError):
            parse_execstart_stable("not an execstart at all")


# --- Tests: Parse correctness ---

class TestParseCorrectness:

    def test_parse_extracts_stable_fields(self):
        result = parse_execstart_stable(PRE_RELOAD_TEXT)
        assert result == ExecStartStable(
            path="/home/ron/.bin/lfm",
            argv="/home/ron/.bin/lfm serve text",
            ignore_errors="no",
        )

    def test_parse_post_reload_same_stable(self):
        pre = parse_execstart_stable(PRE_RELOAD_TEXT)
        post = parse_execstart_stable(POST_RELOAD_TEXT)
        assert pre == post

    def test_execstart_stable_fields_dict(self):
        d = execstart_stable_fields(PRE_RELOAD_TEXT)
        assert d == {
            'path': '/home/ron/.bin/lfm',
            'argv': '/home/ron/.bin/lfm serve text',
            'ignore_errors': 'no',
        }

    def test_complex_argv_with_many_args(self):
        raw = (
            "{ path=/home/ron/Projects/Hyprneuro/python/.venv/bin/python ; "
            "argv[]=/home/ron/Projects/Hyprneuro/python/.venv/bin/python -I /path/to/script.py --flag1 --flag2 --opt=val ; "
            "ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        )
        result = parse_execstart_stable(raw)
        assert result.path == "/home/ron/Projects/Hyprneuro/python/.venv/bin/python"
        assert "--flag1 --flag2 --opt=val" in result.argv
