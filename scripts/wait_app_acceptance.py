#!/usr/bin/env python3
"""Bounded acceptance coordinator wait. A result is NOT human/security evidence.

The reviewed coordinator writes operation-specific completed/failed/cancelled
ONLY after all intended gates, including any genuine human wait, have finished.
Absent, stale, malformed, timeout or cancellation is failure, never approval.
"""
import json
import os
from pathlib import Path
import sys
import time
from prepare_app_release import digest, private_file


def wait(bundle, timeout=7200):
    token=digest(private_file(bundle/'operation.started'))
    result=bundle/'acceptance-result.json'
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if result.exists():
            file=private_file(result)
            if file.stat().st_size>4096: raise RuntimeError('Oversized acceptance coordinator result')
            data=json.loads(file.read_text())
            if (not isinstance(data,dict) or set(data)!={'operation_started_sha256','result'}
                    or data['operation_started_sha256']!=token
                    or data['result'] not in ['completed','failed','cancelled']):
                raise RuntimeError('Stale/malformed acceptance coordinator result')
            return 0 if data['result']=='completed' else 1
        time.sleep(.25)
    return 1


if __name__=='__main__':
    raise SystemExit(wait(Path(sys.argv[1])))
