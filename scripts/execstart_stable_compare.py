#!/usr/bin/env python3
"""
Stable-field comparison for systemd ExecStart structured property.
Version: 2 (corrected per review 01M7KJ4576QVGWW25CXGX5F114)

Closed grammar: EXACT whitelist of known fields. Reject unknown, duplicate,
missing, malformed, multiple commands, oversize. No broad startswith.

Stable fields (compared): path, argv[], ignore_errors
Volatile fields (grammar-validated, content ignored): start_time, stop_time, pid, code, status

Delimiter: ' ; ' — if argv[] itself contains ' ; ', parse FAILS CLOSED.
This is correct: the pinned snapshot commands do NOT contain ' ; ' in argv.
If a future command did, the parse would reject it (fail closed, not silently
misparse).

Length bound: 4096 chars max raw string.

No new dependencies. No D-Bus. No regex. No broad normalization.
"""

from typing import NamedTuple

# --- Closed grammar constants ---

MAX_RAW_LENGTH = 4096
DELIMITER = ' ; '

STABLE_FIELDS = frozenset({'path', 'argv[]', 'ignore_errors'})
VOLATILE_FIELDS = frozenset({'start_time', 'stop_time', 'pid', 'code', 'status'})
ALL_KNOWN_FIELDS = STABLE_FIELDS | VOLATILE_FIELDS


class ExecStartStable(NamedTuple):
    """The stable command-identity fields of an ExecStart entry."""
    path: str
    argv: str
    ignore_errors: str


class ExecStartParseError(ValueError):
    """Raised on any grammar violation."""
    pass


def _extract_field_value(field_str: str, key: str) -> str:
    """Extract value after 'key=' from a field string. Raises if key not present."""
    prefix = key + '='
    if not field_str.startswith(prefix):
        raise ExecStartParseError(f'field does not start with {key!r}')
    return field_str[len(prefix):]


def parse_execstart_stable(raw: str) -> ExecStartStable:
    """Parse an ExecStart string using strict closed grammar.
    
    Raises ExecStartParseError on:
      - oversize (>4096 chars)
      - missing braces
      - unknown field keys
      - duplicate field keys (stable OR volatile)
      - missing required fields (path, argv[], ignore_errors)
      - empty path or argv
      - invalid ignore_errors value (must be 'yes' or 'no')
      - multiple command entries (more than one '{...}' block)
      - delimiter ambiguity (field contains ' ; ' internally, causing
        spurious splits that produce unknown keys)
    """
    # Length bound
    if len(raw) > MAX_RAW_LENGTH:
        raise ExecStartParseError(f'ExecStart oversize: {len(raw)} > {MAX_RAW_LENGTH}')
    
    # Exactly one command block: starts with '{ ' and ends with ' }'
    # Reject multiple commands (multiple '{...}' blocks)
    if raw.count('{ ') != 1 or raw.count(' }') != 1:
        raise ExecStartParseError('ExecStart: expected exactly one command block')
    if not raw.startswith('{ ') or not raw.endswith(' }'):
        raise ExecStartParseError('ExecStart: missing braces')
    
    inner = raw[2:-2]  # strip '{ ' and ' }'
    
    # Split on delimiter
    fields = inner.split(DELIMITER)
    
    # Track seen fields for duplicate detection
    seen = set()
    path = None
    argv = None
    ignore_errors = None
    
    for field in fields:
        # Determine which known key this field belongs to
        matched_key = None
        for key in ALL_KNOWN_FIELDS:
            prefix = key + '='
            if field.startswith(prefix):
                matched_key = key
                break
        
        if matched_key is None:
            # Unknown field — this catches delimiter ambiguity (if argv contained
            # ' ; ', the split would produce fragments that don't match any key)
            raise ExecStartParseError(f'ExecStart: unknown field {field[:40]!r}')
        
        if matched_key in seen:
            raise ExecStartParseError(f'ExecStart: duplicate field {matched_key!r}')
        seen.add(matched_key)
        
        # Extract and validate stable fields
        if matched_key == 'path':
            path = _extract_field_value(field, 'path')
        elif matched_key == 'argv[]':
            argv = _extract_field_value(field, 'argv[]')
        elif matched_key == 'ignore_errors':
            val = _extract_field_value(field, 'ignore_errors')
            if val not in ('yes', 'no'):
                raise ExecStartParseError(f'ExecStart: invalid ignore_errors {val!r}')
            ignore_errors = val
        # Volatile fields: grammar-validated (key present, not duplicate)
        # but content is NOT extracted or compared.
    
    # Complete consumption: all stable fields must be present
    if path is None:
        raise ExecStartParseError('ExecStart: missing path')
    if argv is None:
        raise ExecStartParseError('ExecStart: missing argv[]')
    if ignore_errors is None:
        raise ExecStartParseError('ExecStart: missing ignore_errors')
    
    # Non-empty checks
    if not path:
        raise ExecStartParseError('ExecStart: empty path')
    if not argv:
        raise ExecStartParseError('ExecStart: empty argv[]')
    
    return ExecStartStable(path=path, argv=argv, ignore_errors=ignore_errors)


def compare_execstart_stable(expected_raw: str, actual_raw: str) -> None:
    """Compare two ExecStart strings on stable fields only.
    
    Raises ExecStartParseError if either string is malformed.
    Raises ValueError if stable fields differ.
    Volatile field content is irrelevant (grammar-validated but not compared).
    """
    expected = parse_execstart_stable(expected_raw)
    actual = parse_execstart_stable(actual_raw)
    
    if expected.path != actual.path:
        raise ValueError(f'ExecStart path drift')
    if expected.argv != actual.argv:
        raise ValueError(f'ExecStart argv drift')
    if expected.ignore_errors != actual.ignore_errors:
        raise ValueError(f'ExecStart ignore_errors drift')


def execstart_stable_fields(raw: str) -> dict:
    """Return stable fields as a dict."""
    parsed = parse_execstart_stable(raw)
    return {'path': parsed.path, 'argv': parsed.argv, 'ignore_errors': parsed.ignore_errors}
