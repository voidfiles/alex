from pathlib import Path

import pytest

from alex.lib.locking import LockHeldError, exclusive_lock


def test_exclusive_lock_creates_parent_directory_and_lock_file(tmp_path: Path) -> None:
    lock_path = tmp_path / "sub" / "nested" / "test.lock"

    with exclusive_lock(lock_path):
        assert lock_path.parent.is_dir()
        assert lock_path.exists()


def test_second_acquire_in_process_raises_lock_held(tmp_path: Path) -> None:
    lock_path = tmp_path / "test.lock"

    with exclusive_lock(lock_path):  # noqa: SIM117
        # Each os.open() is a distinct open-file-description, so LOCK_EX|LOCK_NB on
        # the second fd hits EWOULDBLOCK even within the same process.
        with pytest.raises(LockHeldError):
            with exclusive_lock(lock_path):
                pass


def test_lock_released_after_normal_exit(tmp_path: Path) -> None:
    lock_path = tmp_path / "test.lock"

    with exclusive_lock(lock_path):
        pass

    # Should re-acquire without error.
    with exclusive_lock(lock_path):
        assert lock_path.exists()


def test_lock_released_after_exception_in_body(tmp_path: Path) -> None:
    lock_path = tmp_path / "test.lock"

    with pytest.raises(RuntimeError, match="oops"):  # noqa: SIM117
        with exclusive_lock(lock_path):
            raise RuntimeError("oops")

    # Must re-acquire after the body raised.
    with exclusive_lock(lock_path):
        assert lock_path.exists()
