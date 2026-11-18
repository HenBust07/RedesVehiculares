"""Pruebas artificiales: no enumeran ni abren COM reales."""
import csv
from dataclasses import replace
import json
import math
from pathlib import Path
import time
import unittest
import uuid

from captura.p5_lab.controller import Controller
from captura.p5_lab.experiments import Plan
from captura.p5_lab.history import Statistics, load_experiment
from captura.p5_lab.model import Parameters
from captura.p5_lab.protocol import IntegrityError, Monitor, strict_json, validate_record
from captura.p5_lab.synthetic import SyntheticPorts, boot_lines, synthetic_record

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "data/synthetic/p5_lab_tests" / uuid.uuid4().hex[:10]


def wait_for(predicate, timeout=4):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError("Timeout esperando condicion de prueba artificial")


def plan(**changes):
    return replace(Plan("P7", "Controlada", 8, 7, "LAB SINTETICO", "distancia artificial", "Encendido",
        "Activa", "Fixtures en memoria", "NO ES MEDICION REAL", 7,
        {"BUS_001": Parameters(1, .5), "BUS_002": Parameters(2, .25)}), **changes)


def ready_monitor():
    monitor = Monitor("BUS_001")
    for line in boot_lines():
        monitor.consume(line.encode())
    return monitor


def capturing_monitor():
    monitor = ready_monitor()
    monitor.request_start()
    monitor.consume(b"#STATE wifi_initialized mode=NULL promiscuous=1 channel=6 passive=1")
    monitor.consume(b"#STATE capture_started windows=12 window_ms=10000")
    return monitor


class ModelTests(unittest.TestCase):
    def test_large_finite_assumptions_do_not_overflow_statistics(self):
        stats=Statistics();params=Parameters(0,1e-200)
        for unique in [0,3]:
            stats.add({**synthetic_record(unique=unique),'estimated_people':params.estimate(unique),'absolute_error':None})
        result=stats.result()['BUS_001']['estimated_people']
        self.assertTrue(math.isfinite(result['mean']))
        self.assertTrue(math.isfinite(result['sample_stddev']))
        self.assertAlmostEqual(result['mean']/1e200,1.5)

    def test_sample_statistics_and_empty_windows(self):
        stats=Statistics()
        for unique in [0,4,2]:stats.add(synthetic_record(unique=unique))
        result=stats.result()['BUS_001']
        self.assertEqual(result['unique_addresses']['mean'],2)
        self.assertEqual(result['unique_addresses']['sample_stddev'],2)
        self.assertAlmostEqual(result['percent_windows_without_probes'],100/3)
        self.assertEqual(result['rssi_mean_dbm']['n'],2)

    def test_formula_and_floor(self):
        self.assertEqual(Parameters(1, .5).estimate(3), 4)
        self.assertEqual(Parameters(4, .5).estimate(3), 0)
        self.assertEqual(Parameters(0, 1).estimate(0), 0)

    def test_invalid_assumptions(self):
        for background, pd in [(-1,.5),(0,0),(0,-1),(0,1.1),(math.nan,.5),(0,math.inf),(True,.5),(0,1e-320)]:
            with self.subTest(background=background,pd=pd), self.assertRaises(ValueError):
                Parameters(background,pd)

    def test_unknown_reference_and_no_fusion(self):
        stats = Statistics()
        for sensor, unique in [("BUS_001",1),("BUS_002",3)]:
            stats.add({**synthetic_record(sensor, unique=unique), "estimated_people":None,"absolute_error":None})
        summary = stats.result()
        self.assertEqual(set(summary), {"BUS_001","BUS_002"})
        self.assertEqual(summary['BUS_001']['unique_addresses']['mean'],1)
        self.assertIsNone(summary['BUS_001']['unique_addresses']['sample_stddev'])
        self.assertIsNone(summary['BUS_001']['absolute_error']['mean'])


class ProtocolTests(unittest.TestCase):
    def test_pyserial_factory_never_opens_on_construction(self):
        from captura.p5_lab.transport import RealPorts
        connection=RealPorts().create('BUS_001','COM9')
        try:
            self.assertFalse(connection.is_open)
            self.assertIsNone(connection.port)
            self.assertEqual(connection.baudrate,115200)
            self.assertIsNotNone(connection.timeout)
        finally:connection.close()

    def test_missing_final_window_at_stop(self):
        monitor=capturing_monitor();monitor.consume(json.dumps(synthetic_record()).encode())
        with self.assertRaisesRegex(IntegrityError,'MISSING_WINDOW_AT_STOP'):
            monitor.consume(b'#STATE capture_stopped windows=12 elapsed_ms=120000 wifi_stop=ESP_OK')

    def test_strict_json(self):
        for text in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '[]', '{bad}']:
            with self.subTest(text=text), self.assertRaises(IntegrityError):
                strict_json(text)

    def test_record_schema(self):
        for changes in [{"ssid":"not stored"},{"probe_requests":True},{"rssi_mean_dbm":math.nan},
                        {"unique_addresses":513},{"processed_events":99},{"channel":11},{"window_duration_ms":5000}]:
            with self.subTest(changes=changes), self.assertRaises(IntegrityError):
                validate_record({**synthetic_record(),**changes})

    def test_off_radio_identity_is_pending(self):
        monitor=ready_monitor()
        self.assertTrue(monitor.ready)
        self.assertFalse(monitor.identity_verified)
        monitor.request_start()
        self.assertEqual(monitor.mode,'starting')

    def test_sequence_duplicate_gap_restart_and_identity(self):
        for row,code in [(synthetic_record(start_ms=100),'DUPLICATE_WINDOW'),
                         (synthetic_record(start_ms=20100),'MISSING_WINDOW'),
                         (synthetic_record(start_ms=0),'DEVICE_CLOCK_RESET'),
                         (synthetic_record('BUS_002',10100),'IDENTITY_MISMATCH')]:
            monitor=capturing_monitor(); monitor.consume(json.dumps(synthetic_record()).encode())
            with self.subTest(code=code), self.assertRaisesRegex(IntegrityError,code):
                monitor.consume(json.dumps(row).encode())

    def test_corruption_and_unexpected_keys(self):
        for data in [b'{"x":\xff}', b'{"ssid":"secret"}', b'unknown raw text',b'rst:0xc (SW_CPU_RESET)']:
            with self.subTest(data=data),self.assertRaises(IntegrityError):
                capturing_monitor().consume(data)

    def test_intentional_segment_gap(self):
        monitor=capturing_monitor(); monitor.consume(json.dumps(synthetic_record()).encode())
        monitor.request_stop()
        kind, payload=monitor.consume(b'#STATE capture_stopped windows=1 elapsed_ms=13500 wifi_stop=ESP_OK')
        self.assertTrue(payload['intentional']); self.assertEqual(kind,'stopped')
        monitor.request_start()
        monitor.consume(b'#STATE wifi_initialized mode=NULL promiscuous=1 channel=6 passive=1')
        monitor.consume(b'#STATE capture_started windows=12 window_ms=10000')
        monitor.consume(json.dumps(synthetic_record(start_ms=50100)).encode())
        self.assertTrue(monitor.identity_verified)

    def test_incomplete_selftests(self):
        with self.assertRaisesRegex(IntegrityError,'READY_WITHOUT_TESTS'):
            Monitor('BUS_001').consume(b'#READY selftests=PASS radio_disabled=1 commands=START,STOP session_windows=12')


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.root=ARTIFACTS/self._testMethodName
        self.root.mkdir(parents=True)
        self.controllers=[]

    def tearDown(self):
        for ctl in self.controllers:
            ctl.post('shutdown')
            ctl.thread.join(5)
            self.assertFalse(ctl.thread.is_alive())
            self.assertTrue(all(not p.is_open for p in ctl.provider.instances.values()))

    def controller(self, faults=None, interval=.025):
        provider=SyntheticPorts(interval=interval,faults=faults)
        ctl=Controller(self.root,provider,worker_options={'window_timeout':.5,'boot_timeout':2})
        self.controllers.append(ctl)
        for sensor in ('BUS_001','BUS_002'):
            ctl.post('connect',sensor=sensor,port='SIM_'+sensor)
        wait_for(lambda:all(d['ready'] for d in ctl.snapshot()['devices'].values()))
        # Connecting must NOT emit START or create experiment output.
        self.assertFalse(any(b'START\n' in p.writes for p in provider.instances.values()))
        self.assertIsNone(ctl.snapshot()['path'])
        return ctl

    def start(self,ctl,**changes):
        ctl.post('start',plan=plan(**changes),sensors=['BUS_001','BUS_002'],authorized=True)
        wait_for(lambda:ctl.snapshot()['state'] in ('RECORDING','ABORTED','COMPLETE'))

    def test_simultaneous_read_and_automatic_storage(self):
        ctl=self.controller(); self.start(ctl)
        wait_for(lambda:ctl.snapshot()['state']=='COMPLETE')
        wait_for(lambda:all(d.get('port_closed') for d in ctl.snapshot()['devices'].values()))
        data=load_experiment(ctl.snapshot()['path'])
        self.assertEqual(data['metadata']['data_source'],'synthetic')
        self.assertEqual(set(data['statistics']),{'BUS_001','BUS_002'})
        self.assertGreaterEqual(len(data['rows']),20)
        self.assertFalse(data['warnings'])
        self.assertTrue(all(row['model_status']=='NO CALIBRADO' for row in data['rows']))
        for row in data['rows']:
            self.assertEqual(row['absolute_error'],abs(row['estimated_people']-7))
        with (Path(data['path'])/'observations.csv').open(encoding='utf-8-sig') as stream:
            self.assertEqual(len(list(csv.DictReader(stream))),len(data['rows']))

    def test_pause_resume_manual_updates_and_partial_window(self):
        ctl=self.controller(interval=.06); self.start(ctl)
        wait_for(lambda:all(len(r)>=2 for r in ctl.snapshot()['samples'].values()))
        ctl.post('pause'); wait_for(lambda:ctl.snapshot()['state']=='PAUSED')
        before=ctl.snapshot(); time.sleep(.09)
        self.assertEqual(before['elapsed'],ctl.snapshot()['elapsed'])
        self.assertEqual([len(r) for r in before['samples'].values()],[len(r) for r in ctl.snapshot()['samples'].values()])
        ctl.post('manual',count=11); ctl.post('note',text='Observacion SINTETICA sin identificadores')
        ctl.post('resume')
        wait_for(lambda:any(any(r['segment_id']==2 for r in rows) for rows in ctl.snapshot()['samples'].values()))
        ctl.post('stop'); wait_for(lambda:ctl.snapshot()['state']=='COMPLETE')
        data=load_experiment(ctl.snapshot()['path'])
        self.assertTrue(any(r['manual_count']==11 for r in data['rows']))
        self.assertFalse(data['warnings'])
        events=(Path(data['path'])/'events.jsonl').read_text(encoding='utf-8')
        self.assertIn('PAUSE_CONFIRMED',events)
        self.assertIn('PARTIAL_DISCARDED',events)

    def test_faults_abort_both_and_preserve_valid_prefix(self):
        for fault in ['corrupt','gap','duplicate','restart','disconnect','silent','identity','schema']:
            with self.subTest(fault=fault):
                ctl=self.controller({'BUS_001':fault}, interval=.08 if fault=='silent' else .025); self.start(ctl)
                wait_for(lambda:ctl.snapshot()['state']=='ABORTED')
                wait_for(lambda:all(not p.is_open for p in ctl.provider.instances.values()))
                data=load_experiment(ctl.snapshot()['path'])
                self.assertEqual(data['metadata']['status'],'aborted')
                self.assertFalse(data['warnings'])
                self.assertEqual(set(data['metadata']['ports']),{'BUS_001','BUS_002'})
                if fault!='identity': self.assertGreaterEqual(len(data['rows']),1)
                if fault=='schema':
                    text=''.join(p.read_text(encoding='utf-8-sig') for p in Path(data['path']).glob('*') if p.suffix in ('.json','.jsonl','.csv'))
                    self.assertNotIn('FORBIDDEN_SYNTHETIC_FIELD',text)
                ctl.post('shutdown'); ctl.thread.join(3)

    def test_manual_disconnection_closes_both(self):
        ctl=self.controller(interval=.07); self.start(ctl)
        wait_for(lambda:len(ctl.snapshot()['samples']['BUS_001'])>0)
        ctl.post('disconnect',sensor='BUS_001')
        wait_for(lambda:ctl.snapshot()['state']=='ABORTED')
        wait_for(lambda:all(not p.is_open for p in ctl.provider.instances.values()))

    def test_disk_failure_and_host_overflow(self):
        for cause in ['disk','overflow']:
            ctl=self.controller(interval=.07); self.start(ctl)
            wait_for(lambda:len(ctl.snapshot()['samples']['BUS_001'])>0)
            if cause=='disk':
                def fail(_): raise OSError('synthetic disk error')
                ctl.store.observation=fail
            else:
                ctl.overflow.set()
            wait_for(lambda:ctl.snapshot()['state']=='ABORTED')
            wait_for(lambda:all(not p.is_open for p in ctl.provider.instances.values()))
            self.assertGreaterEqual(len(load_experiment(ctl.snapshot()['path'])['rows']),1)
            ctl.post('shutdown'); ctl.thread.join(3)

    def test_authorization_gate(self):
        ctl=self.controller()
        # Test the real authorization gate WITHOUT creating or opening a real transport.
        ctl.provider.data_source='real'
        ctl.post('start',plan=plan(),sensors=['BUS_001'],authorized=False)
        wait_for(lambda:any(e['code']=='OPERATOR_VALIDATION' for e in ctl.snapshot()['events']))
        self.assertIsNone(ctl.snapshot()['path'])
        self.assertFalse(any(b'START\n' in p.writes for p in ctl.provider.instances.values()))
        ctl.provider.data_source='synthetic'

    def test_bridge_mismatch_does_not_open_any_port(self):
        provider=SyntheticPorts()
        ctl=Controller(self.root,provider);self.controllers.append(ctl)
        ctl.post('connect',sensor='BUS_001',port='SIM_BUS_002')
        wait_for(lambda:any(e['code']=='OPERATOR_VALIDATION' for e in ctl.snapshot()['events']))
        self.assertFalse(provider.instances)

    def test_authorized_multiple_firmware_batches(self):
        ctl=self.controller(interval=.01); self.start(ctl,duration_s=1,continue_batches=True)
        wait_for(lambda:ctl.snapshot()['state']=='COMPLETE')
        data=load_experiment(ctl.snapshot()['path'])
        self.assertGreater(max(r['segment_id'] for r in data['rows']),1)
        self.assertFalse(data['warnings'])

    def test_history_corruption_keeps_previous_rows(self):
        ctl=self.controller(); self.start(ctl)
        wait_for(lambda:ctl.snapshot()['state']=='COMPLETE')
        path=Path(ctl.snapshot()['path']); before=load_experiment(path)
        with (path/'observations.jsonl').open('a',encoding='utf-8') as stream: stream.write('{incomplete')
        after=load_experiment(path)
        self.assertEqual(before['rows'],after['rows'])
        self.assertTrue(after['warnings'])


if __name__=='__main__':
    unittest.main()
