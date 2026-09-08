# Contributing

Focused improvements, documentation corrections, and reproducible bug reports are welcome.

## Development

Use Python 3.10 or newer. The maintained source has no external Python dependencies.

```sh
python3 -m unittest discover -s tests -v
python3 src/presentation_kiosk_macro.py --config config/config.example.json --at 2026-09-08T12:00:00
```

The test suite mocks application actions. Do not add CI tests that start or quit a user's tracker, generate input, or activate a LaunchAgent. Test schedule logic and command/error handling without side effects.

## Pull requests

1. Fork the repository and create a focused branch.
2. Change `src/`, tests, or documentation. Preserve `original/presentation_kiosk_macro.py` unchanged.
3. Add meaningful tests for changed schedule or process-control behavior.
4. Update the README for user-visible changes and describe validation limits.
5. Submit small, descriptive commits and explain the resulting behavior in your pull request.

Keep local configurations, credentials, logs, generated plists, and app bundles out of commits. Do not introduce input simulation into the maintained scheduler. Preserve preview as the default and keep live actions explicit.

## Bug reports

Include the macOS version, chip family, Python version, relevant command, expected schedule decision, and actual result. Share a minimal configuration with personal dates/settings removed and redact logs before attaching them.

Distinguish these outcomes: desired state printed in preview; lifecycle request accepted; app actually opened/closed; DeskTime actually recorded the expected session. They are different checks. A report of successful runtime behavior should state which ones were verified.

For a DeskTime account, subscription, authentication, or timesheet issue, use DeskTime's support channels. This project only controls the local application's lifecycle.

Contributions are distributed under the repository's MIT License.
