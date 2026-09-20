#!/usr/bin/env python3
"""Run the suite with the network cut off.

Not a claim in a README — a guard. Any outbound connection that is not to
localhost raises, so "no test touches the internet" is enforced rather than
believed. Localhost is allowed because the HTTP tests bind a real socket.

    python3 scripts/run_tests.py
"""

import socket
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
ALLOWED = {"127.0.0.1", "::1", "localhost"}


class NetworkUsedInTests(AssertionError):
    pass


def _guard(original):
    def wrapper(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ALLOWED:
            raise NetworkUsedInTests(
                f"a test tried to open a connection to {host}. "
                "The suite must run with no network: use the emulator or a fake provider."
            )
        return original(self, address, *args, **kwargs)

    return wrapper


socket.socket.connect = _guard(_real_connect)
socket.socket.connect_ex = _guard(_real_connect_ex)

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    print("\nnetwork guard: active (only localhost was reachable)")
    sys.exit(0 if result.wasSuccessful() else 1)
