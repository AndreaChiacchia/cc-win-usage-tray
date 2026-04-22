"""Focused smoke test for /usage capture settling."""

import os
import queue
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))

from claude_runner import ClaudePtySession


def main():
    session = ClaudePtySession.__new__(ClaudePtySession)
    session._data_queue = queue.Queue()

    def writer():
        session._data_queue.put(
            "Current session 1%usedResets 1pm (Europe/Rome)"
            "Current week 2%usedResets Apr 24, 9am (Europe/Rome)"
        )
        time.sleep(0.1)
        session._data_queue.put(
            "Extra usage 3%used$1.00 / $20.00 spentResets Apr 25"
        )

    threading.Thread(target=writer, daemon=True).start()
    collected = session._collect_until_silent(timeout=1.5, silence=0.25)

    assert "Current session" in collected, collected
    assert "Current week" in collected, collected
    assert "Extra usage" in collected, collected
    print("Usage capture settle test passed")


if __name__ == "__main__":
    main()
