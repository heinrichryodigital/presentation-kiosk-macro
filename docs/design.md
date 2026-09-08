# Design, behavior, and limitations

## Original and maintained versions

| Concern | Original source | Maintained source |
| --- | --- | --- |
| Target | Hardcoded process name `DeskTime` | Configurable bundle identifier |
| Schedule | 07:55–12:00 and 13:00–18:00, every day | Configurable blocks, weekdays, excluded dates |
| During work | Repeatedly checks and reopens target | Reconciles current app state on each invocation |
| Lunch | Stops input simulation but does not quit target | Requests a graceful quit |
| End of day | Repeats `pkill -x` after 18:00 | Requests a normal application quit outside work blocks |
| Idle behavior | Injects Shift after 180 seconds idle, then at random 10–45 second intervals | No input injection or input monitoring |
| Dependencies | PyAutoGUI and pynput | Python standard library and macOS executables |
| Runtime | Indefinite loop, 0.5-second polling | One evaluation per invocation; LaunchAgent runs every 60 seconds |
| Account login/logout | Not implemented | Not implemented |
| Application distribution | Original PyInstaller app | Source and generated user LaunchAgent |

The original has PyAutoGUI's failsafe disabled. Its archive is for provenance, not the recommended installation path. The maintained version deliberately removes synthetic activity so an absence is not disguised by this tool. No original keyboard-monitoring dependencies need to be installed for the maintained scheduler.

## One invocation

1. Read and validate JSON. Reject unknown keys, invalid weekdays/dates/times, overlapping blocks, and overnight blocks.
2. Evaluate the Mac's current local weekday, date, and time. Excluded dates take precedence over work blocks.
3. In preview mode, print the desired state and exit without invoking subprocesses.
4. In apply mode, query the application's running state through macOS JavaScript for Automation (JXA).
5. If a transition is needed, use `open -g -b BUNDLE_ID` or JXA's normal `quit()` request.
6. Report errors with a nonzero exit status, or print the lifecycle request. Matching states produce no output.

The bundle identifier is passed as a subprocess argument, never interpolated into JavaScript or a shell command. No shell is used. Each external command has a 20-second timeout. A failed or unexpected status query prevents any launch/quit request on that invocation. Subsequent scheduled runs try again.

A quit can be delayed or rejected by an application. There is no force termination, explicit flush, or post-request verification. A timeout is an uncertain outcome: the app may still complete the request. Later checks reevaluate its running state.

## Scheduling semantics

The generated LaunchAgent uses `RunAtLoad`, `StartInterval: 60`, and an Aqua session restriction. It stores explicit interpreter, source, config, and log paths. It does not install itself, invoke `sudo`, modify crontab, or enable itself during generation.

Time is the host's local wall clock, not a fixed timezone. Clock or timezone changes affect the next decision. No missed work or break event is backfilled. There is no promise of second-accurate boundaries, wake-on-schedule, or operation while logged out.

The scheduler manages application state throughout the entire day, including weekends. It has no in-app override, holiday calendar integration, tray menu, cross-process lock for manual duplicate invocations, or automatic log rotation. Use a single LaunchAgent and unload it before manually overriding the schedule or running a second copy.

## Permissions and privacy

The maintained program reads only its JSON settings and the configured app's running state for its decisions. It requests launch/quit actions, and writes logs through launchd's stdout/stderr paths. It contains no credential storage, direct network calls, input listeners, or telemetry. The target app itself may perform network activity when launched.

macOS can require Automation permission for application control. Permission approval in one execution host may not carry over to another. No Accessibility or Input Monitoring permission is needed by the maintained source's own logic; the target app has its own requirements.

## DeskTime interpretation

Treat the scheduler as local application lifecycle automation. It cannot guarantee time-record accuracy, session authentication, labeled breaks, or synchronization. Verify these outcomes in DeskTime itself. Refer to the [official usage guide](https://help.desktime.com/hc/en-us/articles/4413021950993-How-to-use-DeskTime) rather than assuming that quitting means an account was signed out.
