from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path

import portalocker


@contextmanager
def vault_lock(lock_file: Path, timeout: float = 5.0):
    """Exclusive cross-platform lock. Raises TimeoutError on timeout."""
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_file, "a+")
    deadline = time.monotonic() + timeout
    while True:
        try:
            portalocker.lock(fh, portalocker.LOCK_EX | portalocker.LOCK_NB)
            break
        except portalocker.exceptions.LockException:
            if time.monotonic() >= deadline:
                fh.close()
                raise TimeoutError(f"Could not acquire lock: {lock_file}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            portalocker.unlock(fh)
        finally:
            fh.close()
