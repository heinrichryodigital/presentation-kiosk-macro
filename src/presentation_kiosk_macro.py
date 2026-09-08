#!/usr/bin/env python3
"""Preview or apply a local macOS application work/break schedule."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import subprocess
import sys
from dataclasses import dataclass

LABEL = "io.github.heinrichryodigital.presentation-kiosk-macro"
DEFAULT_CONFIG = Path.home() / "Library/Application Support/PresentationKioskMacro/config.json"
STATUS_SCRIPT = "function run(argv) { return Application(argv[0]).running() ? 'running' : 'stopped'; }"
QUIT_SCRIPT = "function run(argv) { var app = Application(argv[0]); if (app.running()) app.quit(); }"


@dataclass(frozen=True)
class Schedule:
    app_bundle_id: str
    weekdays: tuple[int, ...]
    work_blocks: tuple[tuple[dt.time, dt.time], ...]
    excluded_dates: tuple[dt.date, ...]

    def wants_running(self, now: dt.datetime) -> bool:
        return (now.isoweekday() in self.weekdays
                and now.date() not in self.excluded_dates
                and any(start <= now.time() < end for start, end in self.work_blocks))


def parse_time(value: object) -> dt.time:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{2}:[0-9]{2}", value):
        raise ValueError("Times must use 24-hour HH:MM format")
    return dt.time.fromisoformat(value)


def load_config(path: Path) -> Schedule:
    raw = json.loads(path.read_text())
    required = {"app_bundle_id", "weekdays", "work_blocks", "excluded_dates"}
    if not isinstance(raw, dict) or set(raw) != required:
        raise ValueError("Config must contain exactly: " + ", ".join(sorted(required)))
    app_id = raw["app_bundle_id"]
    if not isinstance(app_id, str) or not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", app_id):
        raise ValueError("app_bundle_id must be a bundle identifier; see setup instructions")
    days = raw["weekdays"]
    if (not isinstance(days, list) or not days
            or any(type(day) is not int or day not in range(1, 8) for day in days)
            or len(set(days)) != len(days)):
        raise ValueError("weekdays must contain unique integers from 1 (Monday) to 7 (Sunday)")
    blocks = raw["work_blocks"]
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("work_blocks must be a nonempty list")
    parsed = []
    for block in blocks:
        if not isinstance(block, dict) or set(block) != {"start", "end"}:
            raise ValueError("Each work block must contain exactly start and end")
        start, end = parse_time(block["start"]), parse_time(block["end"])
        if start >= end:
            raise ValueError("Each block must end after it starts; overnight blocks are unsupported")
        parsed.append((start, end))
    parsed.sort()
    if any(left[1] > right[0] for left, right in zip(parsed, parsed[1:])):
        raise ValueError("Work blocks must not overlap")
    dates = raw["excluded_dates"]
    if not isinstance(dates, list) or any(not isinstance(d, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", d) for d in dates):
        raise ValueError("excluded_dates must be a list of YYYY-MM-DD dates")
    return Schedule(app_id, tuple(days), tuple(parsed), tuple(dt.date.fromisoformat(d) for d in dates))


def run_command(arguments: list[str]) -> str:
    return subprocess.run(arguments, check=True, capture_output=True, text=True, timeout=20).stdout.strip()


def reconcile(schedule: Schedule, now: dt.datetime, apply: bool = False) -> str:
    desired = schedule.wants_running(now)
    if not apply:
        return f"PREVIEW {now.isoformat(timespec='seconds')}: {schedule.app_bundle_id} should be {'running' if desired else 'stopped'}; no changes made"
    if platform.system() != "Darwin":
        raise ValueError("Applying a schedule requires macOS")
    state = run_command(["/usr/bin/osascript", "-l", "JavaScript", "-e", STATUS_SCRIPT, schedule.app_bundle_id])
    if state not in {"running", "stopped"}:
        raise ValueError(f"Unexpected application status: {state!r}")
    if (state == "running") == desired:
        return ""
    if desired:
        run_command(["/usr/bin/open", "-g", "-b", schedule.app_bundle_id])
        return f"{now.isoformat(timespec='seconds')}: requested launch of {schedule.app_bundle_id}"
    run_command(["/usr/bin/osascript", "-l", "JavaScript", "-e", QUIT_SCRIPT, schedule.app_bundle_id])
    return f"{now.isoformat(timespec='seconds')}: requested graceful quit of {schedule.app_bundle_id}"


def make_launchagent(config: Path, script: Path, python: Path, logs: Path) -> dict:
    return {
        "Label": LABEL,
        "ProgramArguments": [str(python), str(script), "--config", str(config), "--apply"],
        "RunAtLoad": True,
        "StartInterval": 60,
        "ProcessType": "Background",
        "LimitLoadToSessionType": "Aqua",
        "StandardOutPath": str(logs / "scheduler.log"),
        "StandardErrorPath": str(logs / "scheduler-error.log"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Apply the current schedule once (macOS only)")
    mode.add_argument("--write-launchagent", type=Path, metavar="PLIST", help="Write a LaunchAgent without loading it; refuses to overwrite")
    parser.add_argument("--at", help="Preview a local ISO date/time, e.g. 2026-09-08T12:00:00")
    args = parser.parse_args(argv)
    if args.at and (args.apply or args.write_launchagent):
        parser.error("--at is only available in preview mode")
    try:
        config = args.config.expanduser().resolve()
        schedule = load_config(config)
        now = dt.datetime.fromisoformat(args.at) if args.at else dt.datetime.now()
        if now.tzinfo is not None:
            raise ValueError("--at must be a local date/time without a timezone offset")
        if args.write_launchagent:
            if platform.system() != "Darwin":
                raise ValueError("Generating a LaunchAgent requires macOS")
            logs = Path.home() / "Library/Logs/PresentationKioskMacro"
            logs.mkdir(parents=True, exist_ok=True)
            output = args.write_launchagent.expanduser().absolute()
            output.parent.mkdir(parents=True, exist_ok=True)
            # Preserve a virtual environment's executable path rather than resolving its symlink.
            agent = make_launchagent(config, Path(__file__).resolve(), Path(os.path.abspath(sys.executable)), logs)
            with output.open("xb") as stream:
                plistlib.dump(agent, stream)
            print(f"Wrote {output}; not loaded. See README for activation and removal.")
        else:
            message = reconcile(schedule, now, args.apply)
            if message:
                print(message)
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        detail = getattr(error, "stderr", None)
        print(f"Error: {error}" + (f"\n{detail.strip()}" if detail else ""), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
