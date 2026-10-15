"""Offline model routing and provider CLI contract regression tests."""
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'templates/hub/scripts'))
import model_profiles as profiles
import config_check
import operator_common as common

spec = importlib.util.spec_from_file_location('scaffold_profiles', REPO / 'scripts/scaffold_workspace.py')
scaffold = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scaffold)


class ModelProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = (Path(self.tmp.name) / 'workspace with spaces').resolve()
        self.config = json.loads((REPO / 'config/org.example.json').read_text())
        scaffold.scaffold(self.config, self.root)
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')

    def save(self):
        common.write_json(self.root / 'hub/config/org.json', self.config)

    def call(self, *args):
        return subprocess.run([sys.executable, '-B', str(self.root / 'hub/scripts/ops.py'), *args],
                              cwd=self.tmp.name, env=self.env, capture_output=True, text=True, timeout=20)

    def fixture(self, name, body=None, help_ok=True):
        path = self.root / ('fake ' + name)
        body = body or '''
import json, os, sys, subprocess
from pathlib import Path
root = Path(os.environ['OPERATOR_WORKSPACE'])
assert Path.cwd() == root
packet = sys.stdin.read()
assert os.environ['OPERATOR_RUN_ID'] in packet
model = os.environ['OPERATOR_MODEL']
assert sys.argv[sys.argv.index('--model') + 1] == model
if model == 'gpt-6-astra':
    assert sys.argv[1] == 'exec' and sys.argv[-1] == '-'
    assert 'model_reasoning_effort="medium"' in sys.argv
else:
    assert '--print' in sys.argv
    assert sys.argv[sys.argv.index('--effort') + 1] == 'medium'
(root / 'result.txt').write_text('Verified fixture result')
(root / 'args.json').write_text(json.dumps(sys.argv))
subprocess.run([sys.executable, 'hub/scripts/run_close.py', '--run-id', os.environ['OPERATOR_RUN_ID'],
 '--outcome', 'success', '--evidence', 'result.txt', '--check', 'output_verified=pass'], check=True)
'''
        help_text = '--model --config --sandbox --skip-git-repo-check --print --effort --permission-mode --permission-prompts --output-format --settings --allowedTools'
        if not help_ok:
            help_text = 'Legacy CLI: --model only'
        path.write_text('#!' + sys.executable + '\nimport sys\nif "--help" in sys.argv:\n    print(' + repr(help_text) + ')\n    sys.exit(0)\n' + body)
        path.chmod(0o755)
        self.config['runtime']['model_profiles'][name]['executable'] = str(path)
        self.save()
        return path

    def invoke(self, name):
        return self.call('run', 'morning-control-panel', '--profile', name, '--invoke')

    def invocations(self):
        return list((self.root / 'hub/MEMORY/automation-runs').glob('*/invoke.json'))

    def test_builtins_available_without_config_migration(self):
        self.assertEqual(set(profiles.profile_catalog({})), {'gpt-6-astra', 'claude-opus-5-5'})
        self.assertEqual(profiles.resolve_execution({}, profile_name='gpt-6-astra')['effort'], 'medium')

    def test_selection_precedence_and_legacy_wrapper(self):
        runtime = self.config['runtime']
        self.assertEqual(profiles.resolve_execution(self.config)['provider'], 'command')
        runtime['default_profile'] = 'gpt-6-astra'
        self.assertEqual(profiles.resolve_execution(self.config)['profile'], 'gpt-6-astra')
        runtime['automation_profiles'] = {'morning-control-panel': 'claude-opus-5-5'}
        self.assertEqual(profiles.resolve_execution(self.config, 'morning-control-panel')['profile'], 'claude-opus-5-5')
        self.assertEqual(profiles.resolve_execution(self.config, 'morning-control-panel', 'gpt-6-astra')['selected_by'], 'command-line')

    def test_custom_profile_and_partial_builtin_override(self):
        self.config['runtime']['model_profiles'] = {
            'astra-deep': {'provider': 'openai', 'model': 'gpt-6-astra', 'effort': 'xhigh'},
            'claude-opus-5-5': {'effort': 'low', 'timeout_seconds': 240},
        }
        catalog = profiles.profile_catalog(self.config)
        self.assertEqual(catalog['astra-deep']['executable'], 'codex')
        self.assertEqual(catalog['claude-opus-5-5']['timeout_seconds'], 240)
        self.assertEqual(profiles.BUILTIN_PROFILES['claude-opus-5-5']['effort'], 'medium')

    def test_all_supported_efforts_are_forwarded(self):
        for name in profiles.BUILTIN_PROFILES:
            for effort in profiles.EFFORTS:
                with self.subTest(name=name, effort=effort):
                    self.config['runtime']['model_profiles'][name]['effort'] = effort
                    plan = profiles.resolve_execution(self.config, profile_name=name)
                    self.assertIn(effort if name.startswith('claude') else f'model_reasoning_effort="{effort}"', plan['command'])

    def test_invalid_profile_settings_fail_config_check(self):
        cases = [('effort', 'none'), ('effort', 'ultra'), ('model', 'opus'), ('provider', []),
                 ('timeout_seconds', True), ('timeout_seconds', 0), ('executable', ''),
                 ('temperature', 0.2), ('thinking', {'type': 'disabled'}), ('budget_tokens', 100),
                 ('sandbox', 'danger-full-access'), ('command', ['echo'])]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                config = copy.deepcopy(self.config)
                config['runtime']['model_profiles']['gpt-6-astra'][key] = value
                errors, _ = config_check.check_config(config, config)
                self.assertTrue(errors)

    def test_invalid_routes_fail_without_fallback(self):
        for key, value in [('default_profile', 'typo'), ('default_profile', False),
                           ('automation_profiles', []), ('automation_profiles', {'morning-control-panel': 'missing'}),
                           ('automation_profiles', {'wrong-automation': 'gpt-6-astra'}), ('model_profiles', [])]:
            with self.subTest(key=key, value=value):
                config = copy.deepcopy(self.config)
                config['runtime'][key] = value
                with self.assertRaises(ValueError):
                    profiles.resolve_execution(config)

    def test_preview_has_no_run_or_model_side_effects(self):
        self.fixture('gpt-6-astra', "raise RuntimeError('should not run')")
        result = self.call('run', 'morning-control-panel', '--profile', 'gpt-6-astra', '--preview')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan['model'], 'gpt-6-astra')
        self.assertFalse(list((self.root/'hub/MEMORY/automation-runs').glob('*/run.json')))

    def test_unknown_profile_never_creates_packet(self):
        result = self.invoke('typo')
        self.assertEqual(result.returncode, 2)
        self.assertIn('unknown model profile', result.stderr)
        self.assertEqual(self.invocations(), [])
        self.assertFalse(list((self.root/'hub/MEMORY/automation-runs').glob('*/run.json')))

    def test_conflicting_preview_flags_are_rejected(self):
        for flag in ('--preview', '--print-prompt'):
            result = self.call('run', 'morning-control-panel', '--invoke', flag)
            self.assertEqual(result.returncode, 2)
        self.assertEqual(self.invocations(), [])

    def test_codex_fixture_completes_with_evidence_and_profile_receipt(self):
        self.fixture('gpt-6-astra')
        result = self.invoke('gpt-6-astra')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        path = self.invocations()[0]
        receipt = json.loads(path.read_text())
        self.assertTrue(receipt['completed'])
        self.assertEqual(receipt['execution']['provider'], 'openai')
        meta = json.loads(path.with_name('run.json').read_text())
        started = json.loads(path.with_name('started.json').read_text())
        self.assertEqual(meta['execution'], receipt['execution'])
        self.assertEqual(started['execution'], receipt['execution'])
        self.assertEqual(self.call('verify').returncode, 0)

    def test_claude_fixture_completes_with_evidence(self):
        self.fixture('claude-opus-5-5')
        result = self.invoke('claude-opus-5-5')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipt = json.loads(self.invocations()[0].read_text())
        self.assertEqual(receipt['execution']['provider'], 'anthropic')
        self.assertTrue(receipt['completed'])
        self.assertEqual(self.call('verify').returncode, 0)

    def test_provider_exit_zero_without_close_is_incomplete(self):
        for name in profiles.BUILTIN_PROFILES:
            self.fixture(name, 'print("Task finished")')
            self.assertEqual(self.invoke(name).returncode, 3)

    def test_provider_failure_is_recorded_without_fallback(self):
        for name in profiles.BUILTIN_PROFILES:
            self.fixture(name, 'print("Provider unavailable"); sys.exit(9)')
            self.assertEqual(self.invoke(name).returncode, 9)
        self.assertEqual(len(self.invocations()), 2)
        for path in self.invocations():
            receipt = json.loads(path.read_text())
            self.assertFalse(receipt['completed'])
            self.assertEqual(receipt['returncode'], 9)

    def test_missing_cli_fails_before_start(self):
        self.config['runtime']['model_profiles']['gpt-6-astra']['executable'] = '/definitely/missing/codex'
        self.save()
        result = self.invoke('gpt-6-astra')
        self.assertEqual(result.returncode, 2)
        path = self.invocations()[0]
        self.assertFalse(path.with_name('started.json').exists())
        self.assertIn('not found', json.loads(path.read_text())['output_tail'])

    def test_old_cli_fails_before_start_with_update_guidance(self):
        self.fixture('gpt-6-astra', "raise RuntimeError('must not invoke')", help_ok=False)
        result = self.invoke('gpt-6-astra')
        self.assertEqual(result.returncode, 2)
        path = self.invocations()[0]
        self.assertFalse(path.with_name('started.json').exists())
        self.assertIn('update the CLI', json.loads(path.read_text())['output_tail'])

    def test_local_runtime_check_never_runs_the_task(self):
        self.fixture('claude-opus-5-5', "raise RuntimeError('must not invoke')")
        result = self.call('profiles', '--profile', 'claude-opus-5-5', '--check-runtime')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)[0]['runtime_check']['ok'])
        self.assertEqual(self.invocations(), [])

    def test_permission_options_remain_explicit_and_safe(self):
        for name in profiles.BUILTIN_PROFILES:
            command = profiles.resolve_execution(self.config, profile_name=name)['command']
            self.assertNotIn('--dangerously-skip-permissions', command)
            self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', command)
        p = self.config['runtime']['model_profiles']['claude-opus-5-5']
        p['permission_mode'] = 'auto'
        p['allowed_tools'] = ['Read', 'Bash(python3 hub/scripts/run_close.py *)']
        command = profiles.resolve_execution(self.config, profile_name='claude-opus-5-5')['command']
        self.assertIn('auto', command)
        self.assertIn(p['allowed_tools'][1], command)
        p['permission_mode'] = 'bypassPermissions'
        self.assertTrue(profiles.validate_profiles(self.config))

    def test_relative_executable_check_uses_workspace(self):
        path = self.fixture('gpt-6-astra')
        self.config['runtime']['model_profiles']['gpt-6-astra']['executable'] = './' + path.name
        plan = profiles.resolve_execution(self.config, profile_name='gpt-6-astra')
        self.assertTrue(profiles.check_runtime(plan, self.root)['ok'])

    def test_interface_check_timeout_is_actionable(self):
        plan = profiles.resolve_execution(self.config, profile_name='gpt-6-astra')
        with patch.object(profiles.shutil, 'which', return_value='/bin/codex'), patch.object(profiles.subprocess, 'run', side_effect=subprocess.TimeoutExpired('codex', 15)):
            self.assertFalse(profiles.check_runtime(plan, self.root)['ok'])

    def test_timeout_stops_child_from_writing_after_return(self):
        child = 'import time; from pathlib import Path; time.sleep(2); Path("late-write.txt").write_text("bad")'
        self.fixture('gpt-6-astra', 'import subprocess, time\nsubprocess.Popen([sys.executable, "-c", ' + repr(child) + '])\ntime.sleep(10)')
        self.config['runtime']['model_profiles']['gpt-6-astra']['timeout_seconds'] = 1
        self.save()
        result = self.invoke('gpt-6-astra')
        self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
        time.sleep(1.5)
        self.assertFalse((self.root/'late-write.txt').exists())

    def test_packet_only_works_without_agent_configuration(self):
        self.config['runtime'].pop('agent_command')
        self.config['runtime']['automation_profiles'] = {'system-review-loop': 'gpt-6-astra'}
        self.save()
        result = self.call('run', 'morning-control-panel')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.invocations(), [])

    def test_routed_invocation_and_cli_override_reach_correct_provider(self):
        self.fixture('gpt-6-astra')
        self.fixture('claude-opus-5-5')
        self.config['runtime']['default_profile'] = 'gpt-6-astra'
        self.config['runtime']['automation_profiles'] = {'morning-control-panel': 'claude-opus-5-5'}
        self.save()
        result = self.call('run', 'morning-control-panel', '--invoke')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.invoke('gpt-6-astra')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        selections = {(json.loads(p.read_text())['execution']['profile'], json.loads(p.read_text())['execution']['selected_by']) for p in self.invocations()}
        self.assertEqual(selections, {('claude-opus-5-5', 'automation'), ('gpt-6-astra', 'command-line')})

    def test_custom_wrapper_packet_path_and_arguments_are_not_shell_expanded(self):
        command = [sys.executable, '-c', 'pass', '{packet}', '$(do-not-execute)', '`literal`']
        self.config['runtime']['agent_command'] = command
        plan = profiles.resolve_execution(self.config, packet_path=self.root/'packet with spaces.md')
        self.assertEqual(plan['command'][-3:], [str(self.root/'packet with spaces.md'), '$(do-not-execute)', '`literal`'])

    def test_upgrade_adds_profile_helper_without_rewriting_user_config(self):
        for key in ('default_profile', 'automation_profiles', 'model_profiles'):
            self.config['runtime'].pop(key, None)
        self.save()
        config_before = (self.root/'hub/config/org.json').read_bytes()
        (self.root/'hub/scripts/model_profiles.py').unlink()
        result = subprocess.run([sys.executable, str(REPO/'scripts/upgrade_workspace.py'),
                                 '--workspace', str(self.root), '--execute'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root/'hub/scripts/model_profiles.py').exists())
        self.assertEqual(config_before, (self.root/'hub/config/org.json').read_bytes())
        result = self.call('run', 'morning-control-panel', '--profile', 'claude-opus-5-5', '--preview')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['model'], 'claude-opus-5-5')


if __name__ == '__main__':
    unittest.main()
