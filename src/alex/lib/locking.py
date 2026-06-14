"""Mutual-exclusion file lock using fcntl.flock."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class LockHeldError(RuntimeError):
    """Raised when an exclusive lock is already held by another process (or open fd)."""


@contextmanager
def exclusive_lock(lock_path: Path) -> Iterator[None]:
    """Acquire a non-blocking exclusive flock for the duration of the block.

    The lock is tied to the open file descriptor, so it auto-releases on process death
    with no stale PID files to clean up.  LOCK_NB makes a held lock fail immediately
    (raising LockHeldError) rather than blocking — critical for overlap-skip under cron.

    Note: in-process double-acquire works correctly in tests because each os.open() is
    a distinct open-file-description and LOCK_EX|LOCK_NB on the second fd raises
    EWOULDBLOCK.  Do not share the fd; flock on an already-held fd is idempotent.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:  # BlockingIOError (EAGAIN/EWOULDBLOCK) is an OSError
            raise LockHeldError(
                f"Another process holds the lock: {lock_path}"
            ) from error
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
