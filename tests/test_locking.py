import threading
import time
from engram.core.locking import vault_lock

def test_lock_acquires_and_releases(tmp_path):
    lock_file = tmp_path / ".lock"
    with vault_lock(lock_file, timeout=2):
        assert lock_file.exists()
    with vault_lock(lock_file, timeout=2):
        pass

def test_lock_blocks_second_holder(tmp_path):
    lock_file = tmp_path / ".lock"
    timings = []
    def hold():
        with vault_lock(lock_file, timeout=2):
            time.sleep(0.5)
    t = threading.Thread(target=hold)
    t.start()
    time.sleep(0.1)
    start = time.monotonic()
    with vault_lock(lock_file, timeout=2):
        timings.append(time.monotonic() - start)
    t.join()
    assert timings[0] >= 0.3
