import asyncio
import aiohttp
import time

MEXC_FUTURES_PING = "https://contract.mexc.com/api/v1/contract/ping"

REQUESTS = 20
DELAY = 0.3  # сек между запросами


async def ping_once(session: aiohttp.ClientSession) -> float:
    start = time.perf_counter()
    async with session.get(MEXC_FUTURES_PING, timeout=5) as resp:
        await resp.text()
    return (time.perf_counter() - start) * 1000


async def main():
    latencies = []

    timeout = aiohttp.ClientTimeout(total=6)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for i in range(REQUESTS):
            try:
                latency = await ping_once(session)
                latencies.append(latency)
                print(f"[REST] {i+1:02d} latency = {latency:.2f} ms")
            except Exception as e:
                print(f"[REST] {i+1:02d} ERROR: {e}")
            await asyncio.sleep(DELAY)

    if latencies:
        print("\n--- SUMMARY ---")
        print(f"min = {min(latencies):.2f} ms")
        print(f"avg = {sum(latencies)/len(latencies):.2f} ms")
        print(f"max = {max(latencies):.2f} ms")


if __name__ == "__main__":
    asyncio.run(main())

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
