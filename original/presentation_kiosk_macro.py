#!/usr/bin/env python3
"""
macOS presentation kiosk background macro utility.

This utility:
- continuously checks and forces launch of TargetApp during active time shifts,
- monitors physical mouse and keyboard input with pynput,
- tracks in-window inactivity,
- presses Shift with pyautogui after 3 minutes of inactivity, then every
  randomized 10-45 seconds until physical user input resumes or the time
  window closes,
- relentlessly issues pkill terminations to TargetApp from 18:00 (6:00 PM) onwards,
- REMAINS RUNNING indefinitely to auto-resume tracking the following day.
"""

from __future__ import annotations

import datetime as dt
import logging
import platform
import random
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

import pyautogui
from pynput import keyboard, mouse


# --- User configuration ----------------------------------------------------

TargetApp = "DeskTime"

ACTIVE_TIME_BLOCKS = (
    (dt.time(7, 55), dt.time(12, 0)),
    (dt.time(13, 0), dt.time(18, 0)),
)

DAILY_STOP_TIME = dt.time(18, 0)

# The macro wakes up after exactly 3 minutes of total inactivity
INACTIVITY_TRIGGER_SECONDS = 180

# Once active, it types randomly every 10 to 45 seconds (repeating multiple times inside 3 mins)
MIN_SIMULATION_INTERVAL_SECONDS = 10
MAX_SIMULATION_INTERVAL_SECONDS = 45

SIMULATED_KEY = "shift"
PYAUTOGUI_FAILSAFE = False


# --- Internal constants ----------------------------------------------------

POLL_SECONDS = 0.5
SELF_INJECTION_SUPPRESSION_SECONDS = 0.75
LOG_FILE = Path.home() / "Library" / "Logs" / "PresentationKioskMacro.log"


state_lock = threading.Lock()
hardware_input_event = threading.Event()

last_hardware_input_monotonic = time.monotonic()
ignore_keyboard_until_monotonic = 0.0


def configure_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def require_macos() -> None:
    if platform.system() != "Darwin":
        raise SystemExit("This utility is tailored for macOS/Darwin only.")


def active_window_index(now_time: dt.time) -> Optional[int]:
    for index, (start_time, end_time) in enumerate(ACTIVE_TIME_BLOCKS):
        if start_time <= now_time < end_time:
            return index
    return None


def seconds_until_current_window_end(now: dt.datetime) -> float:
    for start_time, end_time in ACTIVE_TIME_BLOCKS:
        if start_time <= now.time() < end_time:
            end_datetime = dt.datetime.combine(now.date(), end_time)
            return max(0.0, (end_datetime - now).total_seconds())
    return 0.0


def maybe_launch_target_app(now: dt.datetime) -> None:
    """Continuously verifies TargetApp is running during active blocks; forces it open if missing."""
    if active_window_index(now.time()) is not None:
        try:
            # Check if the process is running using pgrep (-x looks for exact app name string)
            result = subprocess.run(
                ["pgrep", "-x", TargetApp],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
            # If return code is not 0, it means the app is closed/missing
            if result.returncode != 0:
                logging.info("Target app %s not detected running. Forcing launch.", TargetApp)
                subprocess.Popen(
                    ["open", "-a", TargetApp],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception as e:
            logging.error("Error during continuous process check: %s", str(e))


def maybe_quit_target_app(now: dt.datetime) -> None:
    """Enforces closing of TargetApp via direct process termination from 6 PM onwards."""
    if now.time() >= DAILY_STOP_TIME:
        try:
            # Safely targets background menu daemons without closing the macro itself
            subprocess.run(
                ["pkill", "-x", TargetApp],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        except Exception as e:
            logging.error("Failed to run pkill enforcement command: %s", str(e))


def note_physical_input(source: str) -> None:
    global last_hardware_input_monotonic

    now_monotonic = time.monotonic()
    with state_lock:
        if source == "keyboard" and now_monotonic < ignore_keyboard_until_monotonic:
            return
        last_hardware_input_monotonic = now_monotonic

    hardware_input_event.set()


def on_mouse_move(x: int, y: int) -> None:
    note_physical_input("mouse")


def on_mouse_click(x: int, y: int, button: mouse.Button, pressed: bool) -> None:
    note_physical_input("mouse")


def on_mouse_scroll(x: int, y: int, dx: int, dy: int) -> None:
    note_physical_input("mouse")


def on_key_press(key: object) -> None:
    note_physical_input("keyboard")


def on_key_release(key: object) -> None:
    note_physical_input("keyboard")


def start_input_listeners() -> Tuple[mouse.Listener, keyboard.Listener]:
    mouse_listener = mouse.Listener(
        on_move=on_mouse_move,
        on_click=on_mouse_click,
        on_scroll=on_mouse_scroll,
    )
    keyboard_listener = keyboard.Listener(
        on_press=on_key_press,
        on_release=on_key_release,
    )

    mouse_listener.start()
    keyboard_listener.start()
    logging.info("Started pynput mouse and keyboard listeners.")
    return mouse_listener, keyboard_listener


def inactivity_seconds(window_entered_monotonic: float) -> float:
    with state_lock:
        last_input = last_hardware_input_monotonic

    inactivity_anchor = max(last_input, window_entered_monotonic)
    return max(0.0, time.monotonic() - inactivity_anchor)


def suppress_own_keyboard_event() -> None:
    global ignore_keyboard_until_monotonic

    with state_lock:
        ignore_keyboard_until_monotonic = max(
            ignore_keyboard_until_monotonic,
            time.monotonic() + SELF_INJECTION_SUPPRESSION_SECONDS,
        )


def simulate_shift_key() -> None:
    suppress_own_keyboard_event()
    pyautogui.press(SIMULATED_KEY)
    suppress_own_keyboard_event()
    logging.info("Simulated non-destructive keypress: %s", SIMULATED_KEY)


def run_simulation_sequence(window_entered_monotonic: float) -> None:
    while True:
        now = dt.datetime.now()
        if active_window_index(now.time()) is None:
            logging.info("Stopping simulation sequence: outside active time block.")
            return

        if inactivity_seconds(window_entered_monotonic) < INACTIVITY_TRIGGER_SECONDS:
            logging.info("Stopping simulation sequence: physical input resumed.")
            return

        hardware_input_event.clear()
        if inactivity_seconds(window_entered_monotonic) < INACTIVITY_TRIGGER_SECONDS:
            return

        simulate_shift_key()

        if hardware_input_event.is_set():
            hardware_input_event.clear()
            return

        delay = random.uniform(
            MIN_SIMULATION_INTERVAL_SECONDS,
            MAX_SIMULATION_INTERVAL_SECONDS,
        )
        logging.info("Next simulated keypress in %.1f seconds.", delay)

        delay_deadline = time.monotonic() + delay
        while True:
            now = dt.datetime.now()
            
            # Keep verifying TargetApp execution state even inside wait sequences
            maybe_launch_target_app(now)
            
            if active_window_index(now.time()) is None:
                logging.info("Stopping simulation wait: outside active time block.")
                return

            remaining_delay = delay_deadline - time.monotonic()
            if remaining_delay <= 0:
                break

            remaining_window = seconds_until_current_window_end(now)
            if remaining_window <= 0:
                return

            wait_seconds = min(remaining_delay, remaining_window, POLL_SECONDS)
            if hardware_input_event.wait(timeout=wait_seconds):
                hardware_input_event.clear()
                logging.info("Stopping simulation sequence: hardware input detected.")
                return


def main() -> None:
    require_macos()
    configure_logging()

    pyautogui.FAILSAFE = PYAUTOGUI_FAILSAFE

    logging.info("Starting presentation kiosk macro utility.")
    mouse_listener, keyboard_listener = start_input_listeners()

    active_window: Optional[int] = None
    window_entered_monotonic: Optional[float] = None

    while True:
        now = dt.datetime.now()
        
        # Continuous application policy enforcement checks
        maybe_quit_target_app(now)
        maybe_launch_target_app(now)

        current_window = active_window_index(now.time())
        if current_window is None:
            if active_window is not None:
                logging.info("Left active time block. Standing by...")
            active_window = None
            window_entered_monotonic = None
            hardware_input_event.clear()
            time.sleep(POLL_SECONDS)
            continue

        if current_window != active_window:
            active_window = current_window
            window_entered_monotonic = time.monotonic()
            hardware_input_event.clear()
            logging.info("Entered active time block %s.", current_window + 1)

        if window_entered_monotonic is None:
            window_entered_monotonic = time.monotonic()

        if inactivity_seconds(window_entered_monotonic) >= INACTIVITY_TRIGGER_SECONDS:
            run_simulation_sequence(window_entered_monotonic)
            continue

        remaining_until_trigger = (
            INACTIVITY_TRIGGER_SECONDS - inactivity_seconds(window_entered_monotonic)
        )
        remaining_window = seconds_until_current_window_end(now)
        wait_seconds = min(POLL_SECONDS, remaining_until_trigger, remaining_window)
        if wait_seconds <= 0:
            wait_seconds = POLL_SECONDS

        if not mouse_listener.is_alive() or not keyboard_listener.is_alive():
            logging.error("A pynput listener stopped unexpectedly; exiting.")
            raise SystemExit(1)

        hardware_input_event.wait(timeout=wait_seconds)
        hardware_input_event.clear()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Stopped by KeyboardInterrupt.")
