"""Run each measurement in a fresh process, including native allocations."""

import argparse
import importlib.metadata
import json
import platform
import random
import resource
import shutil
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--table", default="delta_sharing.default.nyctaxi_2019")
    parser.add_argument("--rows", type=int, default=10_000_000)
    parser.add_argument("--repeat", type=int, default=10)
    parser.add_argument("--version", type=int)
    parser.add_argument("--worker")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path)
    return parser.parse_args()


def measure(args, operation):
    started = time.perf_counter()
    rows = operation(args)
    elapsed = time.perf_counter() - started
    assert rows == args.rows, (rows, args.rows)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = peak if sys.platform == "darwin" else peak * 1024
    print(json.dumps({"method": args.worker, "rows": rows,
                      "seconds": elapsed, "peak_mib": peak_bytes / 1024**2}))


def run(args, script, methods):
    import delta_sharing

    profile = json.loads(Path(args.profile).read_text())
    endpoint = urlparse(profile["endpoint"])
    socket.getaddrinfo(endpoint.hostname, endpoint.port or 443)
    if args.version is None:
        args.version = delta_sharing.SharingClient(args.profile).table(args.table).version()
    metadata = {
        "table": args.table, "rows": args.rows, "repetitions": args.repeat,
        "table_version": args.version, "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {name: importlib.metadata.version(name) for name in
                     ("delta-sharing", "pyarrow", "pandas", "duckdb",
                      "delta-kernel-rust-sharing-wrapper")},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    existing = [json.loads(line) for line in args.output.read_text().splitlines()] if args.output.exists() else []
    rng = random.Random(42)
    for repetition in range(args.repeat):
        order = list(methods)
        rng.shuffle(order)
        for method in order:
            if any(r["method"] == method and r["repetition"] == repetition + 1 for r in existing):
                continue
            command = [sys.executable, str(script), "--worker", method,
                       "--profile", args.profile, "--table", args.table,
                       "--rows", str(args.rows), "--version", str(args.version),
                       "--output", str(args.output)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=900)
            if result.returncode:
                raise RuntimeError(f"{method} failed: {result.stderr[-3000:]}")
            row = json.loads(result.stdout.strip().splitlines()[-1])
            row["repetition"] = repetition + 1
            with args.output.open("a") as output:
                output.write(json.dumps(row) + "\n")
            existing.append(row)
            if args.checkpoint_dir:
                args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(args.output, args.checkpoint_dir / args.output.name)
            print(json.dumps(row), flush=True)
    summary = []
    for method in methods:
        samples = [r for r in existing if r["method"] == method]
        seconds = [r["seconds"] for r in samples]
        peaks = [r["peak_mib"] for r in samples]
        summary.append({"method": method, "repetitions": len(samples),
                        "mean_seconds": statistics.mean(seconds),
                        "min_seconds": min(seconds), "max_seconds": max(seconds),
                        "peak_mean_mib": statistics.mean(peaks), "peak_max_mib": max(peaks)})
    args.output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2) + "\n")
