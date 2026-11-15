"""Explicit monotonic command budget; timeout kills/waits only the owned command."""
import time

def timeout(deadline=None,limit=5):
    remaining=limit if deadline is None else deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('Operation command budget exhausted')
    return min(limit,remaining)
