"""Regression cases for authority, evidence, retries, completion, and scoped work."""
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'templates/hub/scripts'))
import operator_common as common
import prepare_workspace as prepare
import lesson_add
import package_gate
import run_automation
import run_close
import deliver_outbox
import memory_health
import schedule_health
import config_check

spec = importlib.util.spec_from_file_location('scaffold_reliability', REPO / 'scripts/scaffold_workspace.py')
scaffold = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scaffold)


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = (Path(self.tmp.name) / 'workspace').resolve()
        config = json.loads((REPO / 'config/org.example.json').read_text())
        config['connectors'] = {}
        config['optional_commands'] = []
        config['runtime']['publisher_targets'] = {}
        config['file_sources'] = {}
        scaffold.scaffold(config, self.root)
        self.config = common.load_config(self.root)
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')

    def call(self, script, *args, cwd=None):
        return subprocess.run([sys.executable, '-B', str(self.root / 'hub/scripts' / script), '--root', str(self.root), *args],
                              cwd=cwd or self.root, env=self.env, text=True, capture_output=True)

    def packet(self, run_id='test', automation='morning-control-panel'):
        path = self.root / 'hub/MEMORY/automation-runs' / run_id
        path.mkdir(parents=True)
        common.write_json(path / 'run.json', {'run_id': run_id, 'automation_id': automation,
            'created_utc': '2026-10-14T12:00:00Z', 'required_checks': ['output_verified']})
        (path / 'run.md').write_text('Finish the fixture task.')
        return path

    def values(self, **updates):
        values = {'outcome': 'success', 'checks': {'output_verified': True}, 'evidence': ['hub/config/org.json'],
                  'improvement': 'none', 'improvement_ref': '', 'lesson': '', 'note': ''}
        values.update(updates)
        return values

    def snapshot(self):
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}

    def test_no_change_runs_do_not_violate_health(self):
        for i in range(7):
            run_close.close_run(self.root, self.config, self.packet(str(i)), self.values(outcome='no_op'))
        health = memory_health.build_report(self.root, self.config)
        self.assertTrue(health['ok'], health)
        self.assertNotIn('recent_runs_without_improvement', [c['name'] for c in health['checks']])

    def test_shared_contract_has_no_quota_or_bulk_lesson_injection(self):
        manifest = run_automation.load_manifest(self.root, self.config)
        text, _ = run_automation.build_run_packet(self.root, self.config, manifest['automations'][0], 'exact-id')
        self.assertEqual(text.count('## Run Contract'), 1)
        self.assertIn('--run-id exact-id', text)
        self.assertNotIn('Leave one improvement', text)
        self.assertNotIn('## Active Lessons', text)

    def test_observe_does_not_write_state(self):
        before = self.snapshot()
        result = subprocess.run([sys.executable, '-B', str(self.root/'hub/scripts/ops.py'), 'observe'],
                                cwd=Path(self.tmp.name), env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_prepare_selects_only_requested_repo_and_preserves_state(self):
        first = self.root / 'work-items/first'
        second = self.root / 'work-items/second'
        first.mkdir(); second.mkdir()
        for path in [first, second]:
            subprocess.run(['git', 'init', '-q', str(path)], check=True)
        self.assertEqual(prepare.selected_repos(self.root, ['work-items/first']), [first.resolve()])
        before = self.snapshot()
        result = self.call('prepare_workspace.py', '--repo', 'work-items/first')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('work-items/second', result.stdout)
        self.assertEqual(before, self.snapshot())

    def test_prepare_rejects_external_or_missing_scope(self):
        for path in ['..', 'missing']:
            with self.assertRaises(ValueError):
                prepare.selected_repos(self.root, [path])

    def test_prepare_stops_on_failed_capability(self):
        result = self.call('prepare_workspace.py', '--repo', 'hub', '--capability', 'command:operator-does-not-exist')
        self.assertEqual(result.returncode, 1)

    def test_close_is_idempotent_and_requires_explicit_amendment(self):
        path = self.packet()
        first = run_close.close_run(self.root, self.config, path, self.values())
        second = run_close.close_run(self.root, self.config, path, self.values())
        self.assertEqual(first, second)
        self.assertEqual(len(run_close.read_chain(run_close.chain_path(self.root, self.config))), 1)
        with self.assertRaises(ValueError):
            run_close.close_run(self.root, self.config, path, self.values(note='changed'))
        amended = run_close.close_run(self.root, self.config, path, self.values(note='corrected evidence note'), amend=True)
        self.assertEqual(amended['revision'], 2)
        self.assertEqual(run_close.verify_chain(self.root, self.config), 0)

    def test_close_recovers_missing_materialized_receipt(self):
        path = self.packet()
        run_close.close_run(self.root, self.config, path, self.values())
        (path/'close.json').unlink()
        run_close.close_run(self.root, self.config, path, self.values())
        self.assertTrue((path/'close.json').exists())
        self.assertEqual(len(run_close.read_chain(run_close.chain_path(self.root, self.config))), 1)

    def test_chain_binds_evidence_and_detects_materialized_tampering(self):
        path = self.packet()
        run_close.close_run(self.root, self.config, path, self.values())
        close = json.loads((path/'close.json').read_text())
        close['note'] = 'unrecorded modification'
        common.write_json(path/'close.json', close)
        self.assertEqual(run_close.verify_chain(self.root, self.config), 1)

    def test_close_rejects_unverified_success_and_empty_blocker(self):
        cases = [{'checks': {}}, {'checks': {'output_verified': False}}, {'evidence': []},
                 {'evidence': ['missing']}, {'checks': []}, {'evidence': 'not-a-list'}, {'outcome': 'blocked', 'note': ''}]
        for index, changes in enumerate(cases):
            path = self.packet(str(index))
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                run_close.close_run(self.root, self.config, path, self.values(**changes))

    def test_latest_refuses_multiple_open_runs(self):
        self.packet('one'); self.packet('two')
        with self.assertRaises(ValueError):
            run_close.find_run_dir(self.root/'hub/MEMORY/automation-runs', '', True)

    def test_run_id_cannot_escape_run_root(self):
        with self.assertRaises(ValueError):
            run_close.find_run_dir(self.root/'hub/MEMORY/automation-runs', '../../outside', False)

    def test_invocation_uses_workspace_and_stdin_but_unclosed_exit_fails(self):
        path = self.packet()
        self.config['runtime']['agent_command'] = [sys.executable, '-c', 'import os,sys; print(os.getcwd()); print(sys.stdin.read()); print(os.environ["OPERATOR_RUN_ID"])']
        code = run_automation.invoke_agent(self.root, self.config, path, path/'run.md')
        self.assertEqual(code, 3)
        result = json.loads((path/'invoke.json').read_text())
        self.assertIn(str(self.root), result['output_tail'])
        self.assertIn('Finish the fixture task.', result['output_tail'])
        self.assertFalse(result['completed'])

    def test_invocation_accepts_verified_close(self):
        path = self.packet()
        agent = "import os,subprocess,sys; subprocess.run([sys.executable,'hub/scripts/run_close.py','--run-id',os.environ['OPERATOR_RUN_ID'],'--outcome','success','--check','output_verified=pass','--evidence','hub/config/org.json'],check=True)"
        self.config['runtime']['agent_command'] = [sys.executable, '-c', agent]
        self.assertEqual(run_automation.invoke_agent(self.root, self.config, path, path/'run.md'), 0)

    def test_invocation_rejects_unchained_close(self):
        path = self.packet()
        common.write_json(path/'close.json', {**self.values(), 'run_id': 'test', 'automation_id': 'morning-control-panel'})
        self.config['runtime']['agent_command'] = [sys.executable, '-c', 'pass']
        self.assertEqual(run_automation.invoke_agent(self.root, self.config, path, path/'run.md'), 3)

    def test_generated_run_ids_do_not_collide(self):
        for _ in range(3):
            result = self.call('run_automation.py', '--automation-id', 'morning-control-panel')
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(list((self.root/'hub/MEMORY/automation-runs').glob('*/run.json'))), 3)

    def test_opposite_lessons_never_merge(self):
        lesson_add.add_lesson(self.root, self.config, 'Always send external messages without explicit approval.', 'case-a')
        with self.assertRaises(SystemExit):
            lesson_add.add_lesson(self.root, self.config, 'Never send external messages without explicit approval.', 'case-b')
        text = (self.root/'hub/MEMORY/LESSONS.md').read_text()
        self.assertIn('hits: 1', text)
        self.assertNotIn('hits: 2', text)

    def test_repeat_evidence_does_not_reinforce_lesson(self):
        rule = 'Verify the destination before delivery.'
        for evidence in ['case-a', 'case-a', 'case-b', 'case-a']:
            lesson_add.add_lesson(self.root, self.config, rule, evidence)
        self.assertIn('hits: 2', (self.root/'hub/MEMORY/LESSONS.md').read_text())

    def test_fuzzy_pruning_is_rejected(self):
        lesson_add.add_lesson(self.root, self.config, 'Verify the destination before delivery.', 'case-a')
        with self.assertRaises(SystemExit):
            lesson_add.prune_lesson(self.root, self.config, 'destination before delivery')

    def work_item(self):
        path = self.root/'work-items/case'
        (path/'source').mkdir(parents=True)
        (path/'metadata').mkdir()
        (path/'README.md').write_text('Owner: Alex\nRequest: summarize source\nDecision boundary: draft only\n')
        (path/'source/input.txt').write_text('source evidence')
        (path/'metadata/map.csv').write_text('file,meaning\ninput.txt,source request\n')
        return path

    def test_gate_valid_mapping_and_context(self):
        result = package_gate.evaluate(self.work_item())
        self.assertTrue(result['ok'], result)

    def test_gate_rejects_empty_files_and_keyword_only_context(self):
        path = self.work_item()
        (path/'README.md').write_text('owner request')
        (path/'source/input.txt').write_text('')
        (path/'metadata/map.csv').write_text('')
        result = package_gate.evaluate(path)
        self.assertFalse(result['ok'])
        self.assertIn('nonempty_files', result['missing'])
        self.assertIn('context_fields', result['missing'])
        self.assertIn('source_mapping', result['missing'])
        self.assertTrue(package_gate.evaluate(path, 'structure')['ok'])

    def test_gate_rejects_unmapped_and_ambiguous_sources(self):
        path = self.work_item()
        (path/'source/extra.txt').write_text('unmapped')
        self.assertFalse(package_gate.evaluate(path)['ok'])
        (path/'source/extra.txt').unlink()
        (path/'source/nested').mkdir()
        (path/'source/nested/input.txt').write_text('ambiguous')
        self.assertFalse(package_gate.evaluate(path)['ok'])
        (path/'metadata/map.csv').write_text('file,meaning\nsource/input.txt,first\nsource/nested/input.txt,second\n')
        self.assertTrue(package_gate.evaluate(path)['ok'])

    def delivery_payload(self):
        path = self.root/'outbox.json'
        counter = self.root/'counter.txt'
        code = f"from pathlib import Path; p=Path({str(counter)!r}); p.write_text(p.read_text()+'sent\\n' if p.exists() else 'sent\\n')"
        payload = {'delivery_id': 'fixture', 'publisher': 'status', 'title': 'test', 'message': 'test',
                   'publisher_config': {'delivery': {'type': 'command', 'command': [sys.executable, '-c', code]}}}
        common.write_json(path, payload)
        return path, payload, counter

    def test_delivery_retry_sends_once(self):
        path, payload, counter = self.delivery_payload()
        for _ in range(2):
            code, _ = deliver_outbox.deliver_once(self.root, self.config, path, payload, True)
            self.assertEqual(code, 0)
        self.assertEqual(counter.read_text(), 'sent\n')

    def test_concurrent_delivery_sends_once(self):
        path, _, counter = self.delivery_payload()
        command = [sys.executable, '-B', str(self.root/'hub/scripts/deliver_outbox.py'), '--root', str(self.root), '--outbox-item', str(path), '--execute']
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env, text=True) for _ in range(2)]
        for proc in processes:
            out, err = proc.communicate(timeout=10)
            self.assertEqual(proc.returncode, 0, out+err)
        self.assertEqual(counter.read_text(), 'sent\n')

    def test_uncertain_delivery_requires_reconciliation(self):
        path, payload, _ = self.delivery_payload()
        with patch.object(deliver_outbox, 'deliver', return_value=(124, 'timeout')) as send:
            first = deliver_outbox.deliver_once(self.root, self.config, path, payload, True)
            second = deliver_outbox.deliver_once(self.root, self.config, path, payload, True)
            self.assertEqual(first[0], 124)
            self.assertEqual(second[0], 2)
            self.assertEqual(send.call_count, 1)
        self.assertEqual(deliver_outbox.deliver_once(self.root, self.config, path, payload, False, resolution='not-delivered')[0], 2)
        self.assertEqual(deliver_outbox.deliver_once(self.root, self.config, path, payload, False, resolution='not-delivered', evidence='destination search verified absent')[0], 0)
        self.assertEqual(deliver_outbox.deliver_once(self.root, self.config, path, payload, True)[0], 0)

    def test_modified_reserved_payload_is_rejected(self):
        path, payload, _ = self.delivery_payload()
        deliver_outbox.deliver_once(self.root, self.config, path, payload, True)
        payload['message'] = 'changed'
        self.assertEqual(deliver_outbox.deliver_once(self.root, self.config, path, payload, True)[0], 2)

    def test_legacy_delivery_receipt_prevents_resend(self):
        path, payload, counter = self.delivery_payload()
        deliver_outbox.write_receipt(self.root, self.config, path, payload, payload['publisher_config']['delivery'], True, 0, 'previous success')
        self.assertEqual(deliver_outbox.deliver_once(self.root, self.config, path, payload, True)[0], 0)
        self.assertFalse(counter.exists())

    def test_schedule_tracks_actual_weekday_occurrence(self):
        now = datetime(2026,10,14,12,46,tzinfo=timezone.utc)
        due = schedule_health.latest_due('*/30 * * * 1-5', 'America/New_York', now)
        self.assertEqual(due, datetime(2026,10,14,12,30,tzinfo=timezone.utc))
        sunday = datetime(2026,10,18,14,tzinfo=timezone.utc)
        self.assertEqual(schedule_health.latest_due('0 8 * * 1-5','America/New_York',sunday), datetime(2026,10,16,12,tzinfo=timezone.utc))

    def test_schedule_handles_dst_and_list_range_step_fields(self):
        spring = datetime(2026,3,8,8,tzinfo=timezone.utc)
        self.assertEqual(schedule_health.latest_due('30 2 * * *','America/New_York',spring), datetime(2026,3,7,7,30,tzinfo=timezone.utc))
        fall = datetime(2026,11,1,7,tzinfo=timezone.utc)
        self.assertEqual(schedule_health.latest_due('30 1 * * *','America/New_York',fall), datetime(2026,11,1,6,30,tzinfo=timezone.utc))
        _, fields = schedule_health.parse_cron('0,30 8-16/2 * * 1-5')
        self.assertEqual(fields[1], {8,10,12,14,16})

    def test_packet_and_process_exit_do_not_count_as_completion(self):
        self.packet()
        self.config['automation_schedules'] = {'morning-control-panel': {'enabled': True, 'cron': '*/30 * * * 1-5', 'timezone':'UTC'}}
        result = common.heartbeat_status(self.root,self.config,datetime(2026,10,14,12,46,tzinfo=timezone.utc))[0]
        self.assertEqual(result['status'], 'overdue')
        self.assertEqual(result['last_run'], '')
        self.assertEqual(result['expected_utc'], '2026-10-14T12:30:00Z')

    def test_invalid_schedule_fails_configuration(self):
        for cron, zone in [('99 * * * *','UTC'), ('0 8 * * *','No/SuchZone')]:
            config = copy.deepcopy(self.config)
            config['automation_schedules'] = {'bad': {'enabled':True,'cron':cron,'timezone':zone}}
            errors, _ = config_check.check_config(config, config)
            self.assertTrue(errors)


    def test_concurrent_close_appends_one_receipt(self):
        self.packet()
        command = [sys.executable, '-B', str(self.root/'hub/scripts/run_close.py'), '--root', str(self.root),
                   '--run-id', 'test', '--outcome', 'success', '--check', 'output_verified=pass', '--evidence', 'hub/config/org.json']
        workers = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env, text=True) for _ in range(2)]
        for worker in workers:
            out, err = worker.communicate(timeout=10)
            self.assertEqual(worker.returncode, 0, out+err)
        self.assertEqual(len(run_close.read_chain(run_close.chain_path(self.root, self.config))), 1)

    def test_legacy_chain_can_be_verified_and_amended(self):
        path = self.packet()
        entry = {'run_id':'test', 'automation_id':'morning-control-panel', 'closed_utc':'2026-01-01T00:00:00Z',
                 'outcome':'success', 'improvement':'none', 'prev_hash':run_close.GENESIS_HASH}
        entry['hash'] = run_close.entry_hash(entry, entry['prev_hash'])
        common.write_text(run_close.chain_path(self.root,self.config), json.dumps(entry)+'\n')
        common.write_json(path/'close.json',entry)
        self.assertEqual(run_close.verify_chain(self.root,self.config),0)
        amended = run_close.close_run(self.root,self.config,path,self.values(note='verify legacy result'),amend=True)
        self.assertEqual(amended['revision'],2)
        self.assertEqual(run_close.verify_chain(self.root,self.config),0)

    def test_reimported_lesson_pack_does_not_add_confirmation(self):
        pack = self.root/'pack.json'
        common.write_json(pack, {'format':1,'name':'fixture','lessons':[{'rule':'Check outputs before closeout.'}]})
        for _ in range(2):
            result = self.call('lesson_pack.py','import','--pack',str(pack),'--execute')
            self.assertEqual(result.returncode,0,result.stderr)
        text = (self.root/'hub/MEMORY/LESSONS.md').read_text()
        self.assertIn('hits: 1',text)
        self.assertNotIn('hits: 2',text)

    def test_retention_preserves_reservations_and_started_runs(self):
        import retention_sweep
        mem = self.root/'hub/MEMORY'
        state = mem/'outbox-delivery-state/20000101-test.json'
        common.write_json(state,{'status':'unknown'})
        run = self.packet('20000101-unfinished')
        common.write_json(run/'started.json',{'started_utc':'2000-01-01T00:00:00Z'})
        expired = retention_sweep.collect_expired(mem,['outbox-delivery-state','indexes','automation-runs','..'],datetime(2026,1,1).date())
        self.assertNotIn(state,expired)
        self.assertNotIn(run,expired)

    def test_uninvoked_packets_do_not_fail_execution_health(self):
        for i in range(8):
            self.packet(str(i))
        self.assertEqual(memory_health.run_close_stats(self.root,self.config)[1],0)
        self.assertTrue(memory_health.build_report(self.root,self.config)['ok'])

    def test_dirty_behind_repo_is_never_auto_stashed(self):
        import sync_workspace
        repo = self.root/'work-items/repo'
        repo.mkdir(parents=True)
        def fake_git(path,args):
            if args[:2] == ['status','--porcelain']: return 0,' M evidence.txt',''
            if args[:2] == ['rev-parse','--abbrev-ref']:
                return 0,('origin/main' if '@{u}' in args else 'main'),''
            if args[:1] == ['rev-list']: return 0,'0 1',''
            if args == ['stash','list']: return 0,'',''
            if args[:1] == ['fetch']: return 0,'',''
            raise AssertionError('unexpected mutation: '+str(args))
        with patch.object(sync_workspace,'run_git',side_effect=fake_git):
            status = sync_workspace.status_for_repo(self.root,repo,True)
        self.assertEqual(status.action,'needs_stash_sync')

    def test_scoped_prepare_stops_on_repo_failure(self):
        from sync_workspace import RepoStatus
        repo = self.root/'hub'
        failed = RepoStatus('hub','main','origin/main',0,0,False,'fetch_failed','fixture failure',(),0)
        with patch.object(prepare,'selected_repos',return_value=[repo]), patch.object(prepare,'status_for_repo',return_value=failed), \
             patch.object(sys,'argv',['prepare_workspace.py','--root',str(self.root),'--repo','hub']):
            self.assertEqual(prepare.main(),1)


    def test_late_completion_of_old_packet_does_not_cover_new_occurrence(self):
        path = self.packet()
        self.config['automation_schedules'] = {'morning-control-panel': {'enabled':True,'cron':'*/30 * * * 1-5','timezone':'UTC'}}
        close = {**self.values(), 'run_id':'test', 'automation_id':'morning-control-panel', 'closed_utc':'2026-10-14T12:40:00Z'}
        common.write_json(path/'close.json',close)
        now = datetime(2026,10,14,12,46,tzinfo=timezone.utc)
        self.assertEqual(common.heartbeat_status(self.root,self.config,now)[0]['status'],'overdue')
        meta = json.loads((path/'run.json').read_text())
        meta['created_utc'] = '2026-10-14T12:30:00Z'
        common.write_json(path/'run.json',meta)
        self.assertEqual(common.heartbeat_status(self.root,self.config,now)[0]['status'],'ok')


if __name__ == '__main__':
    unittest.main()
