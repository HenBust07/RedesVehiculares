"""Prueba funcional de nuestros widgets Tk, exclusivamente con transportes sinteticos."""
import csv
import json
from pathlib import Path
import time
import uuid

from .app import LabApp
from .history import export_csv, load_experiment
from .plots import draw
from .synthetic import SyntheticPorts


def run(window, project):
    out=Path(project)/'results/lab_v1'/('gui-'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    provider=SyntheticPorts(interval=.4)
    app=LabApp(window,project,provider=provider)
    result={'data_source':'synthetic','real_ports_opened':False,'radio_used':False,'checks':{},'errors':[]}
    state={'phase':'connect','began':time.monotonic(),'manual_updated':False,'beats':0,'last':time.monotonic(),'max_gap':0.,'active_max_gap':0.}
    window.report_callback_exception=lambda kind,value,traceback:failure(f'{kind.__name__}: {value}')

    def failure(message):
        if not app.closing:
            result['errors'].append(str(message))
            snapshot=app.controller.snapshot()
            result['failure_phase']=state['phase']
            result['failure_state']=snapshot['state']
            result['failure_events']=snapshot['events'][-8:]
            app.close()

    app.error=failure
    for key,value in {'preset':'P7','mode':'Controlada','duration':'120','phones':'5',
        'location':'INTERFAZ SINTETICA','distance':'fixture sin distancia real','activity':'emulacion sin radio',
        'wifi_state':'Encendido','screen':'Activa','manual_count':'3'}.items():
        app.variables[key].set(value)
    for sensor in ('BUS_001','BUS_002'):
        app.selected[sensor].set(True)
        app.model_enabled[sensor].set(True)
        app.b_values[sensor].set('1' if sensor=='BUS_001' else '0')
        app.p_values[sensor].set('0.5' if sensor=='BUS_001' else '0.25')
    app.notes.insert('1.0','AUTOPRUEBA: datos artificiales, parametros supuestos, NO CALIBRADO')
    app.preset_description()

    def heartbeat():
        now=time.monotonic();gap=now-state['last'];state['max_gap']=max(state['max_gap'],gap);state['last']=now
        if app.controller.snapshot()['state']=='RECORDING':state['active_max_gap']=max(state['active_max_gap'],gap)
        state['beats']+=1
        if not app.closing:window.after(100,heartbeat)

    def check_layout():
        """Measure actual overflow and reachability, not just existence of yview()."""
        result['layout_measurements']=[]
        initial=(window.winfo_width(),window.winfo_height())
        result['checks']['initial_window_fits_screen']=(initial[0]+32<=window.winfo_screenwidth()
            and initial[1]+64<=window.winfo_screenheight())
        for width,height in [(1280,650),(1024,600),(800,500)]:
            window.geometry(f'{width}x{height}+0+0');window.update()
            footer=app.status_label
            assert footer.winfo_y()+footer.winfo_height()<=window.winfo_height(), f'Footer clipped at {window.winfo_geometry()}: {footer.winfo_y()}+{footer.winfo_height()}'
            for name,tab,canvas,last in [
                ('live',app.live_tab,app.live_scroll_canvas,app.destination),
                ('history',app.history_tab,app.history_scroll_canvas,app.history_canvas.get_tk_widget()),
                ('experiment',app.experiment_tab,app.experiment_canvas,None),
                ('events',app.events_tab,app.events_scroll_canvas,app.events_box)]:
                app.right.select(tab);window.update_idletasks()
                bounds=canvas.bbox('all')
                assert bounds[3]>canvas.winfo_height(), f'{name}: no vertical overflow at {width}'
                canvas.yview_moveto(1);canvas.xview_moveto(1);window.update_idletasks()
                assert canvas.yview()[1]>.99, f'{name}: cannot reach bottom'
                assert canvas.xview()[1]>.99, f'{name}: cannot reach right'
                if last is not None:
                    bottom=last.winfo_rooty()+last.winfo_height()
                    assert bottom<=canvas.winfo_rooty()+canvas.winfo_height()+2, f'{name}: last widget clipped'
                result['layout_measurements'].append({'window':[width,height],'tab':name,
                    'viewport':[canvas.winfo_width(),canvas.winfo_height()],
                    'content':list(bounds),'bottom_reachable':True,'right_reachable':True})
                canvas.yview_moveto(0);canvas.xview_moveto(0)
            app.sidebar_canvas.yview_moveto(1);window.update_idletasks()
            assert app.channel_button.winfo_rooty()+app.channel_button.winfo_height()<=app.sidebar_canvas.winfo_rooty()+app.sidebar_canvas.winfo_height()+2
            app.sidebar_canvas.yview_moveto(0)
        app.right.select(app.live_tab)
        window.geometry(f'{initial[0]}x{initial[1]}+16+16');window.update_idletasks()
        canvas=app.live_scroll_canvas
        canvas.yview_moveto(0)
        app.start_button.event_generate('<MouseWheel>',delta=-120)
        window.update_idletasks()
        assert canvas.yview()[0]>0, 'Mouse wheel did not scroll from a child control'
        canvas.yview_moveto(0)
        result['checks']['responsive_layout_three_sizes_four_tabs']=True
        result['checks']['mouse_wheel_from_child']=True

    def step():
        try:
            if app.closing:return
            if time.monotonic()-state['began']>30:raise AssertionError('Timeout de autoprueba GUI')
            snap=app.controller.snapshot()
            phase=state['phase']
            if phase=='connect':
                check_layout()
                state['began']=time.monotonic()
                result['checks']['scrollable_sidebar']=bool(app.sidebar_canvas.yview())
                result['checks']['scrollable_experiment_form']=bool(app.experiment_canvas.yview())
                result['checks']['AP_disabled']=str(app.ap_button['state'])=='disabled'
                result['checks']['channel_change_disabled']=str(app.channel_button['state'])=='disabled'
                result['checks']['no_automatic_capture']=all(not p.writes for p in provider.instances.values())
                for sensor in ('BUS_001','BUS_002'):app.connect_buttons[sensor].invoke()
                state['phase']='ready'
            elif phase=='ready' and all(d['ready'] for d in snap['devices'].values()) and str(app.start_button['state'])=='normal':
                result['checks']['pending_identity_before_START']=all(not d['identity_verified'] for d in snap['devices'].values())
                result['checks']['no_START_on_connect']=all(b'START\n' not in p.writes for p in provider.instances.values())
                app.start_button.invoke();state['phase']='pause'
            elif phase=='pause' and snap['state']=='RECORDING' and str(app.pause_button['state'])=='normal' and all(len(rows)>=2 for rows in snap['samples'].values()):
                app.manual_value.set('8');app.manual_button.invoke()
                app.pause_button.invoke();state['phase']='resume'
            elif phase=='resume' and snap['state']=='PAUSED' and str(app.resume_button['state'])=='normal':
                result['checks']['pause_confirmed']=True
                app.resume_button.invoke();state['phase']='stop'
            elif phase=='stop' and snap['state']=='RECORDING' and str(app.stop_button['state'])=='normal' and all(sum(r['segment_id']==2 for r in rows)>=2 for rows in snap['samples'].values()):
                app.stop_button.invoke();state['phase']='history'
            elif phase=='history' and snap['state']=='COMPLETE' and all(d.get('port_closed') for d in snap['devices'].values()):
                dataset=load_experiment(snap['path'])
                assert not dataset['warnings']
                result['checks']['two_sensors_read']=set(dataset['statistics'])=={'BUS_001','BUS_002'}
                result['checks']['identities_verified']=all(d['identity_verified'] for d in snap['devices'].values())
                result['checks']['manual_counts_3_and_8']={r['manual_count'] for r in dataset['rows']}=={3,8}
                result['checks']['models_independent']={r['pd'] for r in dataset['rows']}=={.5,.25}
                result['checks']['same_bus_distinct_probes']=({r['bus_id'] for r in dataset['rows']}=={'BUS_001'}
                    and {r['probe_id'] for r in dataset['rows']}=={'SENSOR_01','SENSOR_02'})
                result['checks']['serial_id_preserved']=all(r['probe_id']==('SENSOR_01' if r['sensor_id']=='BUS_001' else 'SENSOR_02') for r in dataset['rows'])
                result['checks']['no_calibrated_claim']=all(r['model_status']=='NO CALIBRADO' for r in dataset['rows'])
                result['checks']['ports_closed']=all(not p.is_open for p in provider.instances.values())
                result['experiment_path']=dataset['path']
                result['rows']=len(dataset['rows'])
                export_csv(dataset,out/'synthetic-export.csv')
                with (out/'synthetic-export.csv').open(encoding='utf-8-sig') as stream:
                    result['checks']['csv_round_trip']=len(list(csv.DictReader(stream)))==len(dataset['rows'])
                origin=app.controller.origin
                app.live_plot.update(snap['samples'],[((stamp-origin)/1e9,count) for stamp,count in snap['manual']])
                app.figure.savefig(out/'synthetic-live.png',dpi=140)
                app.load_path(dataset['path']);state['phase']='loaded'
            elif phase=='loaded' and len(app.history)==1:
                result['checks']['history_loaded']=len(app.history_table.get_children())==2
                app.history_figure.savefig(out/'synthetic-history.png',dpi=140)
                result['checks']['png_created']=all((out/name).stat().st_size>10000 for name in ['synthetic-live.png','synthetic-history.png'])
                result['checks']['Tk_event_loop_progressed']=state['beats']>=5
                result['Tk_heartbeat_max_gap_seconds']=state['max_gap']
                result['Tk_active_heartbeat_max_gap_seconds']=state['active_max_gap']
                result['Tk_geometry']=window.winfo_geometry()
                result['checks']['widgets_created']=app.root.winfo_exists()==1
                app.close();return
            if not app.closing:window.after(100,step)
        except Exception as exc:failure(exc)

    window.after(100,heartbeat)
    window.after(400,step)
    window.mainloop()
    result['checks']['coordinator_stopped']=not app.controller.thread.is_alive()
    result['checks']['all_fake_ports_closed_after_GUI']=all(not p.is_open for p in provider.instances.values())
    result['passed']=bool(result['checks']) and all(result['checks'].values()) and not result['errors']
    (out/'report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'output':str(out),**result},indent=2,ensure_ascii=False))
    return 0 if result['passed'] else 1
