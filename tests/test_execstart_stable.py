#!/usr/bin/env python3
"""
Private fixture tests for execstart_stable_compare v2.
Corrected per review 01M7KJ4576QVGWW25CXGX5F114.

BEFORE (fail): pre-fix full-string comparison would reject post-daemon-reload
AFTER (pass): post-fix stable-field comparison accepts post-reload ExecStart
              while rejecting all grammar violations and identity changes.

Run: /home/ron/Projects/Hyprneuro/python/.venv/bin/python -I -m pytest tests/test_execstart_stable.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from execstart_stable_compare import (
    MAX_RAW_LENGTH,
    ExecStartStable,
    ExecStartParseError,
    compare_execstart_stable,
    parse_execstart_stable,
    execstart_stable_fields,
)


# --- Realistic fixtures from actual 04 model snapshot ---

PRE_RELOAD_TEXT = (
    "{ path=/home/ron/.bin/lfm ; argv[]=/home/ron/.bin/lfm serve text ; "
    "ignore_errors=no ; start_time=[Sun 2026-11-15 20:25:30 EST] ; "
    "stop_time=[n/a] ; pid=115653 ; code=(null) ; status=0/0 }"
)

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

# hyprneuro service (complex argv with many flags)
HYPRNEURO_EXECSTART = (
    "{ path=/home/ron/Projects/Hyprneuro/python/.venv/bin/python ; "
    "argv[]=/home/ron/Projects/Hyprneuro/python/.venv/bin/python -I "
    "/home/ron/Workspace/hn-boundary-18aef68-04/source/python/src/hyprneuro/identity_entry.py "
    "broker --root-record /home/ron/Workspace/hn-boundary-18aef68-04/launch-root/launch-root.json "
    "--generation 484e9abe3b334b8c8628df2966394ce8 serve --allow-ingest --watch-hyprland "
    "--assistant-enabled --no-allow-capture --no-allow-on-demand --no-allow-browser "
    "--no-d1-visual --no-retention-enabled ; "
    "ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
)


# --- BEFORE: full string comparison fails ---

class TestBeforeFullStringComparison:
    def test_text_mismatch(self):
        assert PRE_RELOAD_TEXT != POST_RELOAD_TEXT
    def test_omni_mismatch(self):
        assert PRE_RELOAD_OMNI != POST_RELOAD_OMNI
    def test_decision_mismatch(self):
        assert PRE_RELOAD_DECISION != POST_RELOAD_DECISION


# --- AFTER: stable field comparison passes ---

class TestAfterStableFieldComparison:
    def test_text_pass(self):
        compare_execstart_stable(PRE_RELOAD_TEXT, POST_RELOAD_TEXT)
    def test_omni_pass(self):
        compare_execstart_stable(PRE_RELOAD_OMNI, POST_RELOAD_OMNI)
    def test_decision_pass(self):
        compare_execstart_stable(PRE_RELOAD_DECISION, POST_RELOAD_DECISION)
    def test_identical_pass(self):
        compare_execstart_stable(PRE_RELOAD_TEXT, PRE_RELOAD_TEXT)
    def test_hyprneuro_complex_argv_parse(self):
        result = parse_execstart_stable(HYPRNEURO_EXECSTART)
        assert result.path == "/home/ron/Projects/Hyprneuro/python/.venv/bin/python"
        assert "--allow-ingest" in result.argv
        assert "--no-retention-enabled" in result.argv
        assert result.ignore_errors == "no"


# --- Rejection: identity changes ---

class TestIdentityChangeRejection:
    def test_path_change(self):
        bad = (
            "{ path=/home/ron/.bin/lfm-UPDATED ; argv[]=/home/ron/.bin/lfm serve text ; "
            "ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        )
        with pytest.raises(ValueError, match="path drift"):
            compare_execstart_stable(PRE_RELOAD_TEXT, bad)

    def test_argv_change(self):
        bad = (
            "{ path=/home/ron/.bin/lfm ; argv[]=/home/ron/.bin/lfm serve text --injected ; "
            "ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        )
        with pytest.raises(ValueError, match="argv drift"):
            compare_execstart_stable(PRE_RELOAD_TEXT, bad)

    def test_ignore_errors_change(self):
        bad = (
            "{ path=/home/ron/.bin/lfm ; argv[]=/home/ron/.bin/lfm serve text ; "
            "ignore_errors=yes ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        )
        with pytest.raises(ValueError, match="ignore_errors drift"):
            compare_execstart_stable(PRE_RELOAD_TEXT, bad)


# --- Grammar: unknown field rejection ---

class TestUnknownFieldRejection:
    def test_unknown_field(self):
        bad = (
            "{ path=/foo ; argv[]=/foo ; ignore_errors=no ; "
            "mystery_field=42 ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        )
        with pytest.raises(ExecStartParseError, match="unknown field"):
            parse_execstart_stable(bad)

    def test_truncated_field(self):
        # Simulates delimiter ambiguity: a field that doesn't match any known key
        bad = "{ path=/foo ; argv[]=/foo ; ignore_errors=no ; start_time=[n/a"
        with pytest.raises(ExecStartParseError):
            parse_execstart_stable(bad)


# --- Grammar: duplicate field rejection (stable AND volatile) ---

class TestDuplicateFieldRejection:
    def test_duplicate_path(self):
        bad = (
            "{ path=/foo ; path=/bar ; argv[]=/foo ; ignore_errors=no ; "
            "start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        )
        with pytest.raises(ExecStartParseError, match="duplicate.*path"):
            parse_execstart_stable(bad)

    def test_duplicate_pid(self):
        bad = (
            "{ path=/foo ; argv[]=/foo ; ignore_errors=no ; "
            "start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; pid=99 ; code=(null) ; status=0/0 }"
        )
        with pytest.raises(ExecStartParseError, match="duplicate.*pid"):
            parse_execstart_stable(bad)

    def test_duplicate_start_time(self):
        bad = (
            "{ path=/foo ; argv[]=/foo ; ignore_errors=no ; "
            "start_time=[n/a] ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        )
        with pytest.raises(ExecStartParseError, match="duplicate.*start_time"):
            parse_execstart_stable(bad)


# --- Grammar: missing field rejection ---

class TestMissingFieldRejection:
    def test_missing_path(self):
        bad = "{ argv[]=/foo ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        with pytest.raises(ExecStartParseError, match="missing path"):
            parse_execstart_stable(bad)

    def test_missing_argv(self):
        bad = "{ path=/foo ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        with pytest.raises(ExecStartParseError, match="missing argv"):
            parse_execstart_stable(bad)

    def test_missing_ignore_errors(self):
        bad = "{ path=/foo ; argv[]=/foo ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        with pytest.raises(ExecStartParseError, match="missing ignore_errors"):
            parse_execstart_stable(bad)


# --- Grammar: malformed / multiple command / oversize ---

class TestMalformedRejection:
    def test_no_braces(self):
        with pytest.raises(ExecStartParseError):
            parse_execstart_stable("path=/foo ; argv[]=/foo")

    def test_multiple_commands(self):
        bad = (
            "{ path=/foo ; argv[]=/foo ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 } "
            "{ path=/bar ; argv[]=/bar ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        )
        with pytest.raises(ExecStartParseError, match="exactly one command"):
            parse_execstart_stable(bad)

    def test_oversize(self):
        # Exceed 4096 char limit
        padding = "x" * (MAX_RAW_LENGTH)
        bad = f"{{ path=/foo ; argv[]=/foo{padding} ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }}"
        with pytest.raises(ExecStartParseError, match="oversize"):
            parse_execstart_stable(bad)

    def test_empty_string(self):
        with pytest.raises(ExecStartParseError):
            parse_execstart_stable("")

    def test_garbage(self):
        with pytest.raises(ExecStartParseError):
            parse_execstart_stable("not an execstart")

    def test_malformed_trailing(self):
        # Trailing garbage after closing brace
        bad = PRE_RELOAD_TEXT + " extra"
        with pytest.raises(ExecStartParseError):
            parse_execstart_stable(bad)

    def test_empty_path(self):
        bad = "{ path= ; argv[]=/foo ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        with pytest.raises(ExecStartParseError, match="empty path"):
            parse_execstart_stable(bad)

    def test_empty_argv(self):
        bad = "{ path=/foo ; argv[]= ; ignore_errors=no ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        with pytest.raises(ExecStartParseError, match="empty argv"):
            parse_execstart_stable(bad)

    def test_invalid_ignore_errors(self):
        bad = "{ path=/foo ; argv[]=/foo ; ignore_errors=maybe ; start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        with pytest.raises(ExecStartParseError, match="invalid ignore_errors"):
            parse_execstart_stable(bad)


# --- Delimiter ambiguity: FAIL CLOSED ---

class TestDelimiterAmbiguity:
    """If argv contains ' ; ', the split produces fragments that don't match
    any known key → rejected as unknown field. This is correct fail-closed
    behavior: we do NOT assert systemd never produces this, we just reject it."""

    def test_argv_with_delimiter_rejected(self):
        # Simulates argv containing ' ; ' which would cause misparse
        bad = (
            "{ path=/foo ; argv[]=/foo bar ; baz ; ignore_errors=no ; "
            "start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
        )
        with pytest.raises(ExecStartParseError, match="unknown field"):
            parse_execstart_stable(bad)


# --- Parse correctness ---

class TestParseCorrectness:
    def test_extracts_stable(self):
        r = parse_execstart_stable(PRE_RELOAD_TEXT)
        assert r == ExecStartStable(
            path="/home/ron/.bin/lfm",
            argv="/home/ron/.bin/lfm serve text",
            ignore_errors="no",
        )

    def test_pre_post_same_stable(self):
        assert parse_execstart_stable(PRE_RELOAD_TEXT) == parse_execstart_stable(POST_RELOAD_TEXT)

    def test_dict_form(self):
        d = execstart_stable_fields(PRE_RELOAD_TEXT)
        assert d == {'path': '/home/ron/.bin/lfm', 'argv': '/home/ron/.bin/lfm serve text', 'ignore_errors': 'no'}
