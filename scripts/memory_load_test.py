#!/usr/bin/env python3
"""Load / benchmark script for Memory Bank preferences via the Control Plane runtime API.

Runs a configurable number of writes (inserts) and reads, measures throughput and latency, and
produces a cost estimate from unit prices you supply. Stdlib only — no extra dependencies.

Writes go through the governed runtime API (which persists to Vertex Memory Bank); reads use
`resolve`. With managed generation disabled (this deployment), a write is an explicit
`memories.create` and a read is `memories.retrieve` — no per-op Gemini generation tokens — so cost is
modelled per operation. Supply `--price-per-write` / `--price-per-read` from current Vertex AI Memory
Bank / Agent Engine pricing; they default to 0 (the script then just reports counts + latency).

Examples:
  python3 scripts/memory_load_test.py --writes 500 --reads 500 --concurrency 16
  python3 scripts/memory_load_test.py --write-mode canonical --attribute grocery.preferred_snack --writes 200
  python3 scripts/memory_load_test.py --users 50 --writes 1000 --reads 2000 \
      --price-per-write 0.00002 --price-per-read 0.000005
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

P = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
P.add_argument("--base", default="http://localhost:8080")
P.add_argument("--agent", default="grocery-agent")
P.add_argument("--domain", default="grocery")
P.add_argument("--app", default="loadtest")
P.add_argument("--writes", type=int, default=100, help="number of write (insert) operations")
P.add_argument("--reads", type=int, default=100, help="number of read (resolve) operations")
P.add_argument("--users", type=int, default=1, help="spread ops across this many distinct users")
P.add_argument("--concurrency", type=int, default=8)
P.add_argument("--rate", type=float, default=0.0,
               help="max ops/sec per phase (0 = unlimited). Vertex Memory Bank enforces a "
                    "read-requests-per-minute-per-region quota; throttle to stay under it.")
P.add_argument("--write-mode", choices=["dynamic", "canonical"], default="dynamic")
P.add_argument("--topic", default="shopping", help="approved topic for --write-mode dynamic")
P.add_argument("--attribute", default=None, help="writable attribute for --write-mode canonical")
P.add_argument("--price-per-write", type=float, default=0.0, help="flat USD per write op (storage/API)")
P.add_argument("--price-per-read", type=float, default=0.0, help="flat USD per read op (storage/API)")
# Token-based model pricing (e.g. the managed-generation path). gemini-3.5-flash: 1.50 / 9.00.
P.add_argument("--price-in-per-m", type=float, default=0.0, help="USD per 1M input tokens")
P.add_argument("--price-out-per-m", type=float, default=0.0, help="USD per 1M output tokens")
P.add_argument("--tokens-in-write", type=int, default=0, help="model input tokens per write (generation)")
P.add_argument("--tokens-out-write", type=int, default=0, help="model output tokens per write (generation)")
P.add_argument("--tokens-in-read", type=int, default=0, help="model input tokens per read")
P.add_argument("--tokens-out-read", type=int, default=0, help="model output tokens per read")
P.add_argument("--no-cleanup", action="store_true", help="do not forget the test users afterward")
OPTS = P.parse_args()

RUN = int(time.time())


def user_id(i: int) -> str:
    return f"load-{RUN}-{i % max(1, OPTS.users)}"


def call(method: str, path: str, body: dict) -> tuple[int, float]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        OPTS.base + path, data=data, method=method,
        headers={"Content-Type": "application/json", "X-Agent-ID": OPTS.agent},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req) as resp:
            resp.read()
            code = resp.getcode()
    except urllib.error.HTTPError as exc:
        exc.read()
        code = exc.code
    except Exception:
        code = 0
    return code, (time.perf_counter() - started) * 1000.0


def scope(i: int) -> dict:
    return {"userId": user_id(i), "appName": OPTS.app, "domain": OPTS.domain}


def do_write(i: int) -> tuple[int, float]:
    if OPTS.write_mode == "dynamic":
        return call("POST", "/api/v1/runtime/memory/dynamic",
                    {"scope": scope(i), "topic": OPTS.topic, "value": f"load value {i}", "source": "user_directed"})
    return call("PUT", f"/api/v1/runtime/preferences/{OPTS.attribute}",
                {"scope": scope(i), "value": f"value-{i}", "source": "user_directed"})


def do_read(i: int) -> tuple[int, float]:
    return call("POST", "/api/v1/runtime/preferences/resolve",
                {"scope": scope(i), "sessionId": f"s{i}", "agentId": OPTS.agent})


def discover_attribute() -> str | None:
    code, _ = call("POST", "/api/v1/runtime/preferences/resolve",
                   {"scope": scope(0), "sessionId": "probe", "agentId": OPTS.agent})
    if code != 200:
        return None
    req = urllib.request.Request(
        OPTS.base + "/api/v1/runtime/preferences/resolve",
        data=json.dumps({"scope": scope(0), "sessionId": "probe", "agentId": OPTS.agent}).encode(),
        method="POST", headers={"Content-Type": "application/json", "X-Agent-ID": OPTS.agent},
    )
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())
    writable = body.get("writablePreferences") or []
    return writable[0] if writable else None


def run_phase(name: str, fn, count: int) -> dict:
    if count <= 0:
        return {"name": name, "count": 0}
    latencies: list[float] = []
    codes: dict[int, int] = {}
    started = time.perf_counter()
    interval = 1.0 / OPTS.rate if OPTS.rate > 0 else 0.0
    with ThreadPoolExecutor(max_workers=OPTS.concurrency) as pool:
        futures = []
        for i in range(count):
            if interval:
                target = started + i * interval
                delay = target - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
            futures.append(pool.submit(fn, i))
        for fut in as_completed(futures):
            code, ms = fut.result()
            latencies.append(ms)
            codes[code] = codes.get(code, 0) + 1
    wall = time.perf_counter() - started
    ok = sum(v for c, v in codes.items() if 200 <= c < 300)
    latencies.sort()

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        return latencies[min(len(latencies) - 1, int(len(latencies) * p))]

    return {
        "name": name, "count": count, "ok": ok, "codes": codes, "wall_s": wall,
        "throughput": count / wall if wall else 0.0,
        "avg_ms": statistics.mean(latencies) if latencies else 0.0,
        "p50_ms": pct(0.50), "p95_ms": pct(0.95), "p99_ms": pct(0.99),
        "max_ms": latencies[-1] if latencies else 0.0,
    }


def report_phase(r: dict) -> None:
    if not r.get("count"):
        return
    print(f"\n## {r['name']}: {r['count']} ops, {r['ok']} ok  ({dict(sorted(r['codes'].items()))})")
    print(f"   throughput: {r['throughput']:.1f} ops/s over {r['wall_s']:.2f}s")
    print(f"   latency ms: avg={r['avg_ms']:.1f}  p50={r['p50_ms']:.1f}  p95={r['p95_ms']:.1f}  p99={r['p99_ms']:.1f}  max={r['max_ms']:.1f}")


def main() -> int:
    if OPTS.write_mode == "canonical" and not OPTS.attribute:
        OPTS.attribute = discover_attribute()
        if not OPTS.attribute:
            print("Could not discover a writable attribute; pass --attribute. Aborting.")
            return 2
        print(f"Using discovered writable attribute: {OPTS.attribute}")

    print(f"# Memory load test  (base={OPTS.base}, agent={OPTS.agent}, domain={OPTS.domain})")
    print(f"  writes={OPTS.writes} reads={OPTS.reads} users={OPTS.users} concurrency={OPTS.concurrency} "
          f"write_mode={OPTS.write_mode} target={OPTS.attribute or OPTS.topic}")

    writes = run_phase("WRITE (insert)", do_write, OPTS.writes)
    reads = run_phase("READ (resolve)", do_read, OPTS.reads)
    report_phase(writes)
    report_phase(reads)

    def token_cost(tin: int, tout: int) -> float:
        return (tin / 1_000_000) * OPTS.price_in_per_m + (tout / 1_000_000) * OPTS.price_out_per_m

    write_token_each = token_cost(OPTS.tokens_in_write, OPTS.tokens_out_write)
    read_token_each = token_cost(OPTS.tokens_in_read, OPTS.tokens_out_read)
    write_each = OPTS.price_per_write + write_token_each
    read_each = OPTS.price_per_read + read_token_each
    write_cost = OPTS.writes * write_each
    read_cost = OPTS.reads * read_each

    print("\n## Cost estimate")
    if OPTS.price_in_per_m or OPTS.price_out_per_m:
        print(f"   model price: ${OPTS.price_in_per_m:.2f}/1M in, ${OPTS.price_out_per_m:.2f}/1M out")
        print(f"   write tokens: {OPTS.tokens_in_write} in + {OPTS.tokens_out_write} out -> ${write_token_each:.6f}/op")
        print(f"   read tokens:  {OPTS.tokens_in_read} in + {OPTS.tokens_out_read} out -> ${read_token_each:.6f}/op")
    if write_each == 0 and read_each == 0:
        print("   (no prices set — pass flat --price-per-* or token --price-*-per-m + --tokens-* to compute cost)")
    print(f"   writes: {OPTS.writes} x ${write_each:.6f} = ${write_cost:.4f}")
    print(f"   reads:  {OPTS.reads} x ${read_each:.6f} = ${read_cost:.4f}")
    print(f"   total:  ${write_cost + read_cost:.4f}")
    print("   NOTE: this deployment runs with managed generation DISABLED, so writes/reads do NOT")
    print("   invoke gemini-3.5-flash per op (a write is memories.create, a read is memories.retrieve).")
    print("   Token pricing above models the managed-generation path; actual per-op model cost here is $0.")

    if not OPTS.no_cleanup:
        print("\n## Cleanup (forget test users)")
        forgotten = 0
        for u in range(max(1, OPTS.users)):
            code, _ = call("POST", "/api/v1/runtime/memory/forget",
                           {"scope": {"userId": user_id(u), "appName": OPTS.app, "domain": OPTS.domain}})
            forgotten += 1 if code == 200 else 0
        print(f"   forgot {forgotten}/{max(1, OPTS.users)} users")

    failed = (writes.get("count", 0) - writes.get("ok", 0)) + (reads.get("count", 0) - reads.get("ok", 0))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
