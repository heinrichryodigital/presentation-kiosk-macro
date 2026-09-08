# Presentation Kiosk Macro

A configurable macOS work-and-break scheduler for DeskTime, originally created as a personal desktop macro. It opens the configured app during work periods and requests a graceful quit during breaks, outside work hours, on days off, and on excluded dates.

The maintained version uses Python's standard library and macOS tools. It does not monitor input or generate artificial activity. The original source is preserved separately in [`original/`](original/) for historical reference.

## Why I made it

I built PresentationKioskMacro to automate the daily routine around DeskTime: start it for work, stop it at the end of the day, and make room for breaks. Publishing it makes the workflow inspectable and configurable for other macOS users instead of tying it to my personal schedule.

The original implementation did not actually quit DeskTime during lunch and included simulated Shift presses after inactivity. The maintained version changes those behaviors to focus on explicit work and break scheduling. See the [original-versus-maintained comparison](docs/design.md).

## What it does—and what “login/logout” means here

This utility controls whether an application is running. **It does not enter credentials, sign into DeskTime, sign out of your account, toggle Private Time, or edit time records.** Sign in manually to DeskTime before using the scheduler. Opening an already authenticated app can resume tracking; quitting can stop tracking, but the scheduler cannot verify server-side records or a successful flush of pending data.

DeskTime documents app startup, account login, quitting, and Private Time as distinct controls. Private Time pauses tracking within the app; this scheduler instead requests that the app quit. Use DeskTime's own controls if you need account logout or a labeled private-time session. [DeskTime usage guide](https://help.desktime.com/hc/en-us/articles/4413021950993-How-to-use-DeskTime), [Private Time documentation](https://help.desktime.com/hc/en-us/articles/4413030598289-What-is-Private-time).

Independent community project; not affiliated with or endorsed by DeskTime or Apple.

## Requirements

- macOS with a logged-in graphical user session.
- Python 3.10 or newer, available as `python3` below. Check with `python3 --version`.
- DeskTime installed and signed in, or another app you intentionally want to schedule.
- macOS may request Automation permission for the host running the quit request. Complete the first live check interactively and inspect logs if background permissions differ.

There are no third-party Python dependencies in the maintained version. Its source is architecture-neutral; neither Intel nor Apple silicon live DeskTime recovery/session behavior has been certified. The historical Desktop executable was an ARM64 build and is not distributed here.

## 1. Download and configure

```sh
git clone https://github.com/heinrichryodigital/presentation-kiosk-macro.git
cd presentation-kiosk-macro
mkdir -p "$HOME/Library/Application Support/PresentationKioskMacro"
cp config/config.example.json "$HOME/Library/Application Support/PresentationKioskMacro/config.json"
```

Find the installed application's bundle identifier without opening it. If DeskTime is installed elsewhere, adjust the path:

```sh
/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' /Applications/DeskTime.app/Contents/Info.plist
```

Edit your local configuration:

```sh
open -e "$HOME/Library/Application Support/PresentationKioskMacro/config.json"
```

Replace `replace.with.installed.bundle-id` with the identifier you just read. Customize your schedule:

```json
{
  "app_bundle_id": "replace.with.installed.bundle-id",
  "weekdays": [1, 2, 3, 4, 5],
  "work_blocks": [
    {"start": "07:55", "end": "12:00"},
    {"start": "13:00", "end": "18:00"}
  ],
  "excluded_dates": []
}
```

- Weekdays use ISO numbering: Monday is `1`, Sunday is `7`.
- Times use the Mac's local clock and 24-hour `HH:MM` format.
- Starts are inclusive; ends are exclusive. At `12:00`, the example requests a quit; at `13:00`, it requests a launch.
- All times outside these blocks request that the app be stopped, including before work and weekends.
- Add dates such as `"2026-12-25"` to `excluded_dates` for holidays or leave.
- Overlapping or overnight blocks are rejected. Overnight scheduling is not supported.

Settings are read again on every run, so editing the JSON changes the next scheduled decision. Keep personal settings outside the public repository.

## 2. Preview before running

These commands do not open or quit anything:

```sh
python3 src/presentation_kiosk_macro.py
python3 src/presentation_kiosk_macro.py --at 2026-09-08T12:00:00
python3 src/presentation_kiosk_macro.py --at 2026-09-08T13:00:00
```

Expected decisions for the sample schedule: stopped at noon, running at 13:00. Preview reports the desired state; it does not inspect the app's current state or validate that the bundle ID is installed. `--at` accepts a local timestamp without an offset and cannot be combined with live execution.

## 3. Apply once

Save work in the target app and ensure the schedule is what you want. This command acts immediately using the current local time:

```sh
python3 src/presentation_kiosk_macro.py --apply
```

If the app already matches the desired state, nothing happens. Otherwise, the scheduler asks macOS to launch it in the background or sends a normal quit request. It does not force-kill an unresponsive application. Output reports a request, not proof that DeskTime recorded a clock-in, clock-out, or break correctly. Check the app and your timeline during the first live trial.

## 4. Enable automatic scheduling with launchd

A per-user LaunchAgent is the macOS scheduling mechanism used here. Apple documents LaunchAgents and timed jobs in its [launchd guide](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html). This is a cron-like recurring job; it is not an installed cron entry.

Keep the cloned repository and Python interpreter in stable locations. Generate the agent:

```sh
python3 src/presentation_kiosk_macro.py --write-launchagent "$HOME/Library/LaunchAgents/io.github.heinrichryodigital.presentation-kiosk-macro.plist"
plutil -lint "$HOME/Library/LaunchAgents/io.github.heinrichryodigital.presentation-kiosk-macro.plist"
```

Generation records absolute paths and creates the log directory. It does not load or run the agent and refuses to overwrite an existing file. Review the generated plist before activation.

Activate it for your logged-in user:

```sh
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/io.github.heinrichryodigital.presentation-kiosk-macro.plist"
```

**Activation applies the current schedule immediately.** The agent then checks approximately every 60 seconds and is loaded on subsequent user logins. It will reopen an app you manually close during work hours, and request a quit if you manually open it outside work hours. Disable the agent for temporary manual control.

The Mac must be awake and logged in. Scheduling is approximate: sleeping, logout, system load, application prompts, and failures can delay actions. Missed boundaries are not replayed as historical clock events; the next invocation evaluates the current schedule. This tool does not wake the Mac.

Do not run the original macro alongside the maintained scheduler: the original may reopen the app or simulate input, conflicting with the new behavior.

## Disable or remove

Unload the job to stop future checks (this does not change the target app's current state):

```sh
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/io.github.heinrichryodigital.presentation-kiosk-macro.plist"
```

For permanent removal, also remove the generated agent:

```sh
rm "$HOME/Library/LaunchAgents/io.github.heinrichryodigital.presentation-kiosk-macro.plist"
```

You may retain your configuration and logs. To regenerate after moving the repository or changing Python, unload and remove the old plist, then repeat generation and activation. To resume an unloaded agent whose plist is retained, use the bootstrap command again.

## Troubleshooting

- **Missing Python:** install a supported Python from [python.org](https://www.python.org/downloads/macos/) and verify its version before generating the agent.
- **App cannot be found:** re-read `CFBundleIdentifier` from the installed app. The example identifier must be replaced.
- **App does not quit:** it may be showing a dialog, denying automation, or be unresponsive. Check it manually; there is no force-kill fallback.
- **Unexpected lunch/weekend behavior:** the app is intentionally stopped whenever the current time is outside all configured work blocks.
- **Tracking does not resume:** check DeskTime authentication and its own tracking/privacy settings. App process state is not account state.
- **Agent fails:** inspect `~/Library/Logs/PresentationKioskMacro/scheduler-error.log` and verify the Python, source, and config paths in its plist. Use `launchctl print "gui/$(id -u)/io.github.heinrichryodigital.presentation-kiosk-macro"` to inspect the loaded job.
- **Manual control keeps being overridden:** unload this agent and check whether the original macro or a separate login item is also running.

Logs contain lifecycle requests and errors. They do not contain keyboard/mouse activity. Log rotation is not built in; periodically inspect or clear old logs while the agent is unloaded.

## Development and provenance

```sh
python3 -m unittest discover -s tests -v
```

Tests mock application-control commands and do not alter your DeskTime session. See [design and limitations](docs/design.md), [original source provenance](docs/provenance.md), and [contribution guidelines](CONTRIBUTING.md).

Released under the [MIT License](LICENSE). No prebuilt, signed, or notarized `.app` release is provided; the maintained distribution is the Python source plus a generated LaunchAgent.
