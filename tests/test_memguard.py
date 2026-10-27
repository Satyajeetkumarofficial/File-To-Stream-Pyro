"""python tests/test_memguard.py -- memory limit detection and size-aware defaults"""
import os, subprocess, sys
ROOT = os.path.join(os.path.dirname(__file__), "..")
BASE = dict(os.environ, API_ID="1", API_HASH="x", BOT_TOKEN="1:x", BIN_CHANNEL="-100123")
CODE = ("import info;print(info.MEMORY_LIMIT_MB, info.MAX_INFLIGHT_CHUNKS, info.MAX_CONCURRENT_STREAMS, info.MAX_CLIENTS)")


def run(mem=None, **extra):
    env = dict(BASE, **extra)
    env.pop("MEMORY_LIMIT_MB", None)
    if mem:
        env["MEMORY_LIMIT_MB"] = str(mem)
    return subprocess.run([sys.executable, "-c", CODE], cwd=ROOT, env=env, capture_output=True, text=True).stdout.split()


small, mid, big = run(512), run(1024), run(4096)
assert small == ["512.0", "16", "12", "0"], small
assert mid == ["1024.0", "48", "32", "0"], mid
assert big == ["4096.0", "128", "100", "0"], big
assert run(512, MAX_INFLIGHT_CHUNKS="40", MAX_CLIENTS="6")[1:] == ["40", "12", "6"]      # env always wins
print("\u2705 512 MB host -> budget 16 MB, 12 streams, ALL bots | 1 GB -> 48/32 | 4 GB -> 128/100 | env overrides")
slow = subprocess.run([sys.executable, "-c", "import info;print(info.SLOW_CPU, info.MAX_CONCURRENT_STREAMS, info.DISK_CACHE_MB)"],
                      cwd=ROOT, env=dict(BASE, CPU_LIMIT="0.1"), capture_output=True, text=True).stdout.split()
assert slow == ["True", "4", "0"], slow
fast = subprocess.run([sys.executable, "-c", "import info;print(info.SLOW_CPU)"], cwd=ROOT,
                      env=dict(BASE, CPU_LIMIT="2"), capture_output=True, text=True).stdout.split()
assert fast == ["False"], fast
print("\u2705 0.1 vCPU host -> 4 streams, cache off | 2 vCPU -> normal")

sys.path.insert(0, ROOT)
import memguard
os.environ["MEMORY_LIMIT_MB"] = "512"
assert memguard.limit_mb() == 512.0 and memguard.rss_mb() > 0 and 0 < memguard.pressure() < 1
memguard.trim()
print("\u2705 memguard: limit=512 MB, rss=%.0f MB, pressure=%.0f%%" % (memguard.rss_mb(), 100 * memguard.pressure()))

assert memguard._parse_cpu_max("10000 100000") == 0.1 and memguard._parse_cpu_max("max 100000") is None
assert memguard._parse_cpu_max("200000 100000") == 2.0
print("\u2705 cgroup cpu.max parsing")
