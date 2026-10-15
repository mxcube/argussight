import ctypes
import signal
import socket
import sys
from typing import Iterable, Union

import Levenshtein

PR_SET_PDEATHSIG = 1


def stop_with_parent() -> None:
    """preexec_fn for subprocess.Popen: the kernel sends SIGTERM to the child
    as soon as argussight dies, even when it is killed with SIGKILL (Linux only).
    The signal is tied to the thread that started the child, so only start
    children with this from threads that live as long as argussight (main thread)
    """
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM)


def find_close_key(d: dict, key: str, max_distance: int = 3) -> Union[str, None]:
    """Return first key in dict whose Levenshtein distance to key is <= max_distance"""
    min_distance = float("inf")
    closest_key = None

    for dict_key in d:
        distance = Levenshtein.distance(key, dict_key)
        if distance < min_distance:
            min_distance = distance
            closest_key = dict_key

    if min_distance <= max_distance:
        return closest_key

    return None


def is_port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)  # Optional: set a short timeout for connection attempt
        result = s.connect_ex(("localhost", port))
        return result != 0  # If result is non-zero, port is free


def find_free_port(start_port=9000, reserved_ports: Iterable[int] = ()):
    """Return first free port from start_port on, skipping reserved_ports
    (ports handed out to processes that might not be listening yet)"""
    port = start_port
    while port in reserved_ports or not is_port_free(port):
        port += 1
    return port
