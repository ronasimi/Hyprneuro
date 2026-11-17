#!/usr/bin/env python3
"""
Stable-field comparison for systemd ExecStart structured property.

Purpose: Compare the COMMAND IDENTITY (path, argv[], ignore_errors) of two
ExecStart strings while IGNORING volatile manager execution bookkeeping
(start_time, stop_time, pid, code, status) that resets on daemon-reload.

Grammar (closed, bounded, no regex):
  { path=WORD ; argv[]=WORDS ; ignore_errors=(yes|no) ; start_time=[...] ; stop_time=[...] ; pid=INT ; code=(...) ; status=INT/INT }

Only ONE command per ExecStart (len==1 after parse). Multiple commands,
missing fields, or malformed serialization are REJECTED.

No new dependencies. No fallback. No broad normalization.
"""

from typing import NamedTuple


class ExecStartStable(NamedTuple):
    """The stable command-identity fields of an ExecStart entry."""
    path: str
    argv: str
    ignore_errors: str


def parse_execstart_stable(raw: str) -> ExecStartStable:
    """Parse an ExecStart string, extracting only stable command fields.
    
    Raises ValueError on any malformed input, missing field, or ambiguity.
    Uses bounded closed-grammar split, NOT regex.
    """
    # Expected format: { field=val ; field=val ; ... }
    if not raw.startswith('{ ') or not raw.endswith(' }'):
        raise ValueError('ExecStart: missing braces')
    
    inner = raw[2:-2]  # strip '{ ' and ' }'
    
    # Split on ' ; ' (the systemd serialization delimiter)
    fields = inner.split(' ; ')
    
    # Extract stable fields by exact prefix match
    path = None
    argv = None
    ignore_errors = None
    
    for field in fields:
        if field.startswith('path='):
            if path is not None:
                raise ValueError('ExecStart: duplicate path field')
            path = field[5:]
        elif field.startswith('argv[]='):
            if argv is not None:
                raise ValueError('ExecStart: duplicate argv field')
            argv = field[7:]
        elif field.startswith('ignore_errors='):
            if ignore_errors is not None:
                raise ValueError('ExecStart: duplicate ignore_errors field')
            val = field[14:]
            if val not in ('yes', 'no'):
                raise ValueError(f'ExecStart: invalid ignore_errors value {val!r}')
            ignore_errors = val
        # Volatile fields (start_time, stop_time, pid, code, status) are
        # present but NOT extracted. Their presence is expected but their
        # values are irrelevant to command identity.
    
    if path is None:
        raise ValueError('ExecStart: missing path field')
    if argv is None:
        raise ValueError('ExecStart: missing argv field')
    if ignore_errors is None:
        raise ValueError('ExecStart: missing ignore_errors field')
    
    # Reject empty path or argv
    if not path:
        raise ValueError('ExecStart: empty path')
    if not argv:
        raise ValueError('ExecStart: empty argv')
    
    return ExecStartStable(path=path, argv=argv, ignore_errors=ignore_errors)


def compare_execstart_stable(expected_raw: str, actual_raw: str) -> None:
    """Compare two ExecStart strings on stable fields only.
    
    Raises ValueError if stable fields differ or either string is malformed.
    Does NOT raise for volatile field differences (pid, start_time, etc).
    """
    expected = parse_execstart_stable(expected_raw)
    actual = parse_execstart_stable(actual_raw)
    
    if expected.path != actual.path:
        raise ValueError(
            f'ExecStart path drift: expected={expected.path!r} actual={actual.path!r}'
        )
    if expected.argv != actual.argv:
        raise ValueError(
            f'ExecStart argv drift: expected={expected.argv!r} actual={actual.argv!r}'
        )
    if expected.ignore_errors != actual.ignore_errors:
        raise ValueError(
            f'ExecStart ignore_errors drift: expected={expected.ignore_errors!r} actual={actual.ignore_errors!r}'
        )


def execstart_stable_fields(raw: str) -> dict:
    """Return the stable fields as a dict (for use in manager_after comparison)."""
    parsed = parse_execstart_stable(raw)
    return {'path': parsed.path, 'argv': parsed.argv, 'ignore_errors': parsed.ignore_errors}
