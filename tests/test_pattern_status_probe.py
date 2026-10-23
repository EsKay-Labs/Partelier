"""Read-only diagnostics identify the loaded product, without running its tools."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pattern_status_probe_test',
    ROOT/'tools/fusion/PatternStatusProbe/PatternStatusProbe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class PatternStatusProbeTests(unittest.TestCase):
    def app(self):
        return NS(version='test', userInterface=NS(activeCommand='active-user-command'))

    def owner(self, request=None):
        runner = NS(_current=request, _command=None, _pending=None, busy=request is not None,
            _stopped=False, _command_id='owned-pattern', _custom_event=object(), _event_id='owned-event')
        return NS(runner=runner, _session=NS(preview=object()), _busy=False, _pending=None,
                  palette_state=Mock(return_value={'phase':'preview','previewCurrent':True}))

    def inspect_owner(self, owner, path=None):
        module = NS(__file__=str(path or ROOT/'Partelier/partelier/addin.py'), _pattern_commands=owner)
        with patch.object(probe.sys, 'modules', {'owned':module}):
            return probe.inspect(self.app())

    def test_completed_native_preview_remains_distinguishable_from_busy_ui(self):
        owner = self.owner()
        result = self.inspect_owner(owner)
        self.assertTrue(result['read_only'])
        self.assertEqual(result['active_command'],'active-user-command')
        status = result['owners'][0]
        self.assertTrue(status['session']['previewCurrent'])
        self.assertTrue(status['has_preview'])
        self.assertFalse(status['runner_busy'])
        self.assertIsNone(status['request'])
        owner.palette_state.assert_called_once_with()

    def test_pending_native_request_reports_lifecycle_flags_without_computing(self):
        request = NS(serial=4, computed=False, executed=False, cancelled=False, prepared=None, error=None)
        owner = self.owner(request)
        owner.runner._command = NS(isValid=True)
        result = self.inspect_owner(owner)['owners'][0]
        self.assertTrue(result['runner_busy'])
        self.assertTrue(result['command_valid'])
        self.assertEqual(result['request'], {'serial':4,'computed':False,'executed':False,
                         'cancelled':False,'has_result':False,'error':None})
        self.assertFalse(request.computed)

    def test_unrelated_or_isolated_test_packages_are_ignored(self):
        owner = self.owner()
        result = self.inspect_owner(owner, ROOT/'tools/fusion/fixtures/addin.py')
        self.assertEqual(result['owners'],[])
        owner.palette_state.assert_not_called()

    def test_unloaded_product_returns_empty_read_only_status(self):
        self.assertEqual(self.inspect_owner(None)['owners'],[])


if __name__ == '__main__':
    unittest.main()
