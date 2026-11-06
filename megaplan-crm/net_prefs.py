"""Same as telegram-bridge/net_prefs.py (each project runs in its own interpreter).

Outbound connections: IPv4 first, resolved addresses remembered for a few minutes.

06.11: the server has an IPv6 route that does not reach Telegram. Python tried the
IPv6 address first and waited for the whole timeout (5 s for sendMessage, 40 s for
other calls) before falling back to IPv4, which answers in 0.07 s. IPv6 stays as a
fallback; nothing is disabled. ``BRIDGE_PREFER_IPV4=0`` turns this off.
"""
import os
import socket
import threading
import time

CACHE_SECONDS = 300
_original = socket.getaddrinfo
_cache = {}
_lock = threading.Lock()


def prefer_ipv4(results):
    """IPv4 answers first, the rest in their original order."""
    return sorted(results, key=lambda item: 0 if item[0] == socket.AF_INET else 1)


def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    key = (host, port, family, type, proto, flags)
    now = time.monotonic()
    with _lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < CACHE_SECONDS:
            return list(cached[1])
    results = prefer_ipv4(_original(host, port, family, type, proto, flags))
    with _lock:
        _cache[key] = (now, results)
    return list(results)


def install():
    if os.environ.get("BRIDGE_PREFER_IPV4", "1") == "0" or socket.getaddrinfo is getaddrinfo:
        return False
    socket.getaddrinfo = getaddrinfo
    return True
