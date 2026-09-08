import contextlib
import datetime as dt
import importlib.util
import io
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('scheduler', ROOT / 'src/presentation_kiosk_macro.py')
scheduler = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = scheduler
spec.loader.exec_module(scheduler)


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / 'config/config.example.json').read_text())
        self.data['app_bundle_id'] = 'com.example.TestApp'
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / 'config.json'

    def load(self):
        self.config.write_text(json.dumps(self.data))
        return scheduler.load_config(self.config)

    def test_boundaries_and_weekend(self):
        schedule = self.load()
        cases = {'2026-09-08T07:54:59': False, '2026-09-08T07:55:00': True,
                 '2026-09-08T11:59:59': True, '2026-09-08T12:00:00': False,
                 '2026-09-08T12:59:59': False, '2026-09-08T13:00:00': True,
                 '2026-09-08T17:59:59': True, '2026-09-08T18:00:00': False,
                 '2026-09-09T00:00:00': False, '2026-09-12T10:00:00': False}
        for stamp, expected in cases.items():
            with self.subTest(stamp=stamp):
                self.assertEqual(schedule.wants_running(dt.datetime.fromisoformat(stamp)), expected)

    def test_holiday(self):
        self.data['excluded_dates'] = ['2026-09-08']
        self.assertFalse(self.load().wants_running(dt.datetime(2026, 9, 8, 10)))

    def test_invalid_config(self):
        bad = [('weekdays', [True]), ('weekdays', [1, 1]), ('weekdays', [8]), ('weekdays', []),
               ('app_bundle_id', 'x"; quit'), ('work_blocks', []),
               ('work_blocks', [{'start': '18:00', 'end': '07:00'}]),
               ('work_blocks', [{'start': '7:00', 'end': '12:00'}]),
               ('work_blocks', [{'start': '25:00', 'end': '26:00'}]),
               ('work_blocks', [{'start': '07:00', 'end': '12:00'}, {'start': '11:00', 'end': '13:00'}]),
               ('excluded_dates', ['2026-02-30']), ('excluded_dates', ['20260908'])]
        baseline = self.data.copy()
        for key, value in bad:
            with self.subTest(key=key, value=value):
                self.data = dict(baseline, **{key: value})
                with self.assertRaises(ValueError):
                    self.load()

    def test_unknown_keys(self):
        self.data['workdays'] = [1]
        with self.assertRaises(ValueError):
            self.load()

    def test_adjacent_blocks_and_sorting(self):
        self.data['work_blocks'] = [{'start': '12:00', 'end': '18:00'}, {'start': '07:00', 'end': '12:00'}]
        self.assertTrue(self.load().wants_running(dt.datetime(2026, 9, 8, 12)))

    def test_preview_has_no_subprocesses(self):
        with patch.object(scheduler, 'run_command') as run:
            self.assertIn('PREVIEW', scheduler.reconcile(self.load(), dt.datetime(2026, 9, 8, 10)))
            run.assert_not_called()

    @patch.object(scheduler.platform, 'system', return_value='Darwin')
    def test_reconciliation(self, system):
        for hour, actual, action in [(10, 'stopped', 'open'), (12, 'running', 'quit'),
                                     (18, 'running', 'quit'), (10, 'running', None), (12, 'stopped', None)]:
            with self.subTest(hour=hour, actual=actual):
                with patch.object(scheduler, 'run_command', side_effect=[actual, '']) as run:
                    result = scheduler.reconcile(self.load(), dt.datetime(2026, 9, 8, hour), True)
                    self.assertEqual(run.call_count, 2 if action else 1)
                    if action == 'open':
                        self.assertEqual(run.call_args.args[0], ['/usr/bin/open', '-g', '-b', 'com.example.TestApp'])
                    elif action == 'quit':
                        self.assertIn(scheduler.QUIT_SCRIPT, run.call_args.args[0])
                    else:
                        self.assertEqual(result, '')

    @patch.object(scheduler.platform, 'system', return_value='Darwin')
    def test_failed_status_never_launches_or_quits(self, system):
        for response in ['unexpected', subprocess.TimeoutExpired('osascript', 20)]:
            with patch.object(scheduler, 'run_command', side_effect=[response]) as run:
                with self.assertRaises((ValueError, subprocess.TimeoutExpired)):
                    scheduler.reconcile(self.load(), dt.datetime(2026, 9, 8, 10), True)
                self.assertEqual(run.call_count, 1)

    @patch.object(scheduler.platform, 'system', return_value='Linux')
    def test_apply_rejects_non_macos(self, system):
        with patch.object(scheduler, 'run_command') as run:
            with self.assertRaises(ValueError):
                scheduler.reconcile(self.load(), dt.datetime(2026, 9, 8, 10), True)
            run.assert_not_called()

    def test_launchagent_paths_with_spaces_roundtrip(self):
        agent = scheduler.make_launchagent(Path('/tmp/My Config/config.json'), Path('/tmp/My Repo/app.py'),
                                          Path('/tmp/My Python/bin/python3'), Path('/tmp/My Logs'))
        decoded = plistlib.loads(plistlib.dumps(agent))
        self.assertEqual(decoded['ProgramArguments'][0], '/tmp/My Python/bin/python3')
        self.assertEqual(decoded['ProgramArguments'][3], '/tmp/My Config/config.json')
        self.assertEqual(decoded['StartInterval'], 60)
        self.assertTrue(decoded['RunAtLoad'])

    def test_cli_rejects_apply_at(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            scheduler.main(['--apply', '--at', '2026-09-08T10:00'])
        self.assertEqual(result.exception.code, 2)

    def test_cli_rejects_timezone(self):
        self.load()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(scheduler.main(['--config', str(self.config), '--at', '2026-09-08T10:00+08:00']), 1)

    @patch.object(scheduler.platform, 'system', return_value='Darwin')
    def test_generate_never_loads_or_overwrites(self, system):
        self.load()
        output = Path(self.temp.name) / 'agent.plist'
        with patch.object(scheduler.Path, 'home', return_value=Path(self.temp.name)), \
                patch.object(scheduler, 'run_command') as run, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            args = ['--config', str(self.config), '--write-launchagent', str(output)]
            self.assertEqual(scheduler.main(args), 0)
            self.assertEqual(scheduler.main(args), 1)
            run.assert_not_called()
        self.assertEqual(plistlib.loads(output.read_bytes())['Label'], scheduler.LABEL)


if __name__ == '__main__':
    unittest.main()
