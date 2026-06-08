from __future__ import annotations

import argparse
from pathlib import Path
import threading
import time

from modelscope.hub.snapshot_download import snapshot_download


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a ModelScope model with size polling.")
    parser.add_argument("model_id")
    parser.add_argument("local_dir")
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()

    target = Path(args.local_dir)
    target.mkdir(parents=True, exist_ok=True)
    stop_event = threading.Event()
    monitor = threading.Thread(
        target=monitor_size,
        args=(target, args.interval, stop_event),
        daemon=True,
    )
    monitor.start()

    print(f"download_start model_id={args.model_id} local_dir={target.resolve()}", flush=True)
    try:
        path = snapshot_download(
            model_id=args.model_id,
            local_dir=str(target),
            max_workers=args.max_workers,
        )
        print(f"download_done path={path}", flush=True)
    finally:
        stop_event.set()
        monitor.join(timeout=2)
        print_size(target, prefix="final")


def monitor_size(target: Path, interval: int, stop_event: threading.Event) -> None:
    while not stop_event.wait(interval):
        print_size(target, prefix="progress")


def print_size(target: Path, *, prefix: str) -> None:
    files = [item for item in target.rglob("*") if item.is_file()]
    total = sum(item.stat().st_size for item in files)
    gib = total / 1024 / 1024 / 1024
    print(f"{prefix} files={len(files)} bytes={total} gib={gib:.2f}", flush=True)


if __name__ == "__main__":
    main()

