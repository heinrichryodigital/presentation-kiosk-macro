# Source provenance

## Recovered project

The author's Desktop application was `PresentationKioskMacro.app`, an ARM64 Mach-O executable built using PyInstaller. Unlike an AppleScript applet, it did not contain a `main.scpt` resource.

A local project contained `outputs/presentation_kiosk_macro.py`, a PyInstaller spec targeting that source, and a built application. The Desktop executable and that project's built app executable have the same SHA-256:

```text
966a1504e697ece372352b026b2db90e5df84cffa466915297eabf32b37338c2
```

The Python source from that project is copied byte-for-byte to `original/presentation_kiosk_macro.py`. Source SHA-256:

```text
577f2545285af243099f6678432f71db5c1bb6618acb1fb19c37df834df42e29
```

This establishes the source project's association with the Desktop build. It is not a reproducible-build proof that the source had no edits after compilation; the embedded Python bytecode was not extracted and compared.

No credentials or personal filesystem paths were found in the published Python source. Its original app name and schedule constants are retained as part of the program. The application binary, bundled third-party dependencies, icon, generated build directories, and local account metadata are not distributed.

## Verification

- Original source was compared byte-for-byte with the recovered project file.
- The maintained scheduler passed 13 unittest cases with application commands mocked, including schedule boundaries, weekends, excluded dates, malformed settings, command failures, and LaunchAgent serialization.
- JXA's read-only running-state query was checked on macOS against Finder and returned `running`.
- No DeskTime launch, quit, account action, input simulation, or LaunchAgent activation was performed during publication.

Runtime DeskTime behavior and macOS permission prompts require a user-controlled integration trial. A successful mocked test does not prove an accurate DeskTime timesheet or successful application quit.

## History

The first commit preserves the original source. Subsequent separately pushed commits introduce the maintained scheduler and tests, document setup and behavior, and add the open-source license, contributor guidance, and automated checks. The original archive remains unchanged.
