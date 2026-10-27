"""
Speed / stability tester for your deployed link.

  python speedtest.py "https://your-app.koyeb.app/12345?hash=abc123" -c 1 4 8 -s 100

-c  list of simultaneous-user counts to try      -s  MB each user downloads (default 100)
It reports per-user and total MB/s, errors, and verifies Range support.
Needs:  pip install aiohttp
"""
import argparse, asyncio, time
import aiohttp


async def one(session, url, mb, start_at=0):
    got, t0 = 0, time.time()
    headers = {"Range": f"bytes={start_at}-{start_at + mb * 1048576 - 1}"}
    try:
        async with session.get(url, headers=headers) as r:
            if r.status not in (200, 206):
                return got, time.time() - t0, f"HTTP {r.status}"
            async for chunk in r.content.iter_chunked(256 * 1024):
                got += len(chunk)
        return got, time.time() - t0, None
    except Exception as e:
        return got, time.time() - t0, repr(e)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("-c", "--users", type=int, nargs="+", default=[1, 4, 8])
    ap.add_argument("-s", "--size", type=int, default=100, help="MB per user")
    a = ap.parse_args()
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=60)
    async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(limit=0)) as s:
        async with s.head(a.url) as r:
            print(f"HEAD -> {r.status}, size={int(r.headers.get('Content-Length', 0))/1048576:.1f} MB, "
                  f"Accept-Ranges={r.headers.get('Accept-Ranges')}")
        for n in a.users:
            t0 = time.time()
            res = await asyncio.gather(*[one(s, a.url, a.size, i * 7 * 1048576) for i in range(n)])
            wall = time.time() - t0
            total = sum(g for g, _, _ in res)
            errs = [e for _, _, e in res if e]
            per = [g / 1048576 / max(t, 1e-6) for g, t, _ in res]
            print(f"{n:>3} user(s): total {total/1048576/wall:7.1f} MB/s | per user min {min(per):6.1f} "
                  f"avg {sum(per)/len(per):6.1f} MB/s | errors: {len(errs)}" + (f" {errs[:2]}" if errs else ""))


asyncio.run(main())
