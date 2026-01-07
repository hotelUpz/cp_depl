# import asyncio
# import aiohttp
# import time

# MEXC_FUTURES_PING = "https://contract.mexc.com/api/v1/contract/ping"

# REQUESTS = 20
# DELAY = 0.3  # сек между запросами


# async def ping_once(session: aiohttp.ClientSession) -> float:
#     start = time.perf_counter()
#     async with session.get(MEXC_FUTURES_PING, timeout=5) as resp:
#         await resp.text()
#     return (time.perf_counter() - start) * 1000


# async def main():
#     latencies = []

#     timeout = aiohttp.ClientTimeout(total=6)
#     async with aiohttp.ClientSession(timeout=timeout) as session:
#         for i in range(REQUESTS):
#             try:
#                 latency = await ping_once(session)
#                 latencies.append(latency)
#                 print(f"[REST] {i+1:02d} latency = {latency:.2f} ms")
#             except Exception as e:
#                 print(f"[REST] {i+1:02d} ERROR: {e}")
#             await asyncio.sleep(DELAY)

#     if latencies:
#         print("\n--- SUMMARY ---")
#         print(f"min = {min(latencies):.2f} ms")
#         print(f"avg = {sum(latencies)/len(latencies):.2f} ms")
#         print(f"max = {max(latencies):.2f} ms")


# if __name__ == "__main__":
#     asyncio.run(main())

# python3 - << 'EOF'
# import asyncio, aiohttp, time

# URL = "https://contract.mexc.com/api/v1/contract/ping"
# N = 20

# async def main():
#     times = []
#     async with aiohttp.ClientSession() as s:
#         for i in range(N):
#             t0 = time.perf_counter()
#             async with s.get(URL) as r:
#                 await r.text()
#             dt = (time.perf_counter() - t0) * 1000
#             times.append(dt)
#             print(f"[REST] {i+1:02d} {dt:.2f} ms")
#             await asyncio.sleep(0.3)

#     print("\nSUMMARY:")
#     print("min =", round(min(times),2), "ms")
#     print("avg =", round(sum(times)/len(times),2), "ms")
#     print("max =", round(max(times),2), "ms")

# asyncio.run(main())
# EOF


from __future__ import annotations

import asyncio
import aiohttp
import ssl
import time
from typing import List


# ============================================================
# CONFIG
# ============================================================

MEXC_FUTURES_PING = "https://contract.mexc.com/api/v1/contract/ping"

REQUESTS = 20
DELAY = 0.3  # seconds between requests

# PROXY_URL = "http://login:password@ip:port"  # <-- ЗАМЕНИ или оставь None
PROXY_URL = "http://Lg7hLbC8:cXxwCBy8@154.219.72.198:64810"
# PROXY_URL = None

# MODE:
# 1 = simple direct session
# 2 = proxy session
# 3 = manager-style (SSL_CTX + proxy)
MODE = 2


# ============================================================
# SSL (MANAGER STYLE)
# ============================================================

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


# ============================================================
# PING LOGIC
# ============================================================

async def ping_once(session: aiohttp.ClientSession) -> float:
    start = time.perf_counter()
    async with session.get(MEXC_FUTURES_PING, timeout=5) as resp:
        await resp.text()
    return (time.perf_counter() - start) * 1000


def print_stats(latencies: List[float]) -> None:
    if not latencies:
        print("\nNO DATA")
        return

    print("\n--- SUMMARY ---")
    print(f"min = {min(latencies):.2f} ms")
    print(f"avg = {sum(latencies) / len(latencies):.2f} ms")
    print(f"max = {max(latencies):.2f} ms")


# ============================================================
# MODE 1 — SIMPLE DIRECT SESSION
# ============================================================

async def run_simple():
    latencies: List[float] = []

    timeout = aiohttp.ClientTimeout(total=6)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for i in range(REQUESTS):
            try:
                latency = await ping_once(session)
                latencies.append(latency)
                print(f"[DIRECT] {i+1:02d} latency = {latency:.2f} ms")
            except Exception as e:
                print(f"[DIRECT] {i+1:02d} ERROR: {e}")
            await asyncio.sleep(DELAY)

    print_stats(latencies)


# ============================================================
# MODE 2 — PROXY SESSION
# ============================================================

async def run_proxy():
    latencies: List[float] = []

    timeout = aiohttp.ClientTimeout(total=6)
    async with aiohttp.ClientSession(
        timeout=timeout,
        proxy=PROXY_URL,
        trust_env=False,
    ) as session:
        for i in range(REQUESTS):
            try:
                latency = await ping_once(session)
                latencies.append(latency)
                print(f"[PROXY ] {i+1:02d} latency = {latency:.2f} ms")
            except Exception as e:
                print(f"[PROXY ] {i+1:02d} ERROR: {e}")
            await asyncio.sleep(DELAY)

    print_stats(latencies)


# ============================================================
# MODE 3 — MANAGER-STYLE (SSL_CTX + PROXY)
# ============================================================

async def run_manager_style():
    latencies: List[float] = []

    connector = aiohttp.TCPConnector(
        ssl=SSL_CTX,
        limit=0,
    )

    timeout = aiohttp.ClientTimeout(total=6)

    async with aiohttp.ClientSession(
        connector=connector,
        proxy=PROXY_URL,
        timeout=timeout,
        trust_env=False,
    ) as session:
        for i in range(REQUESTS):
            try:
                latency = await ping_once(session)
                latencies.append(latency)
                print(f"[MGR   ] {i+1:02d} latency = {latency:.2f} ms")
            except Exception as e:
                print(f"[MGR   ] {i+1:02d} ERROR: {e}")
            await asyncio.sleep(DELAY)

    print_stats(latencies)


# ============================================================
# ENTRY POINT
# ============================================================

async def main():
    if MODE == 1:
        await run_simple()
    elif MODE == 2:
        await run_proxy()
    elif MODE == 3:
        await run_manager_style()
    else:
        raise RuntimeError(f"Unknown MODE={MODE}")


if __name__ == "__main__":
    asyncio.run(main())
