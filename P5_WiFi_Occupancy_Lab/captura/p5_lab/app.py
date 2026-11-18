"""Interfaz Tk. Los lectores, el coordinador y los archivos trabajan fuera de Tk."""
import json
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from .controller import ACTIVE, Controller
from .experiments import PRESETS, Plan
from .history import export_csv, load_experiment
from .model import MODEL_STATUS, Parameters
from .plots import LivePlot, draw, new_figure
from .protocol import SENSORS
from .identity import BUS_ID, PROBE_IDS, probe_label
from .storage import private_text
from .synthetic import SyntheticPorts
from .transport import RealPorts


def number(text):
    return float(text.strip().replace(",", "."))


def optional_count(text):
    return None if not text.strip() else int(text.strip())


def fmt(value, decimals=2):
    return "—" if value is None else f"{value:.{decimals}f}" if isinstance(value, float) else str(value)


class LabApp:
    def __init__(self, root, project, *, demo=False, provider=None):
        self.root, self.project = root, Path(project)
        self.provider = provider or (SyntheticPorts() if demo else RealPorts())
        self.synthetic = self.provider.data_source == "synthetic"
        self.controller = Controller(self.project, self.provider)
        self.history, self.history_queue = [], queue.Queue()
        registry=json.loads((self.project/'config/devices.json').read_text(encoding='utf-8'))
        self.registry={d['firmware']['protocol_sensor_id']:d for d in registry['devices']}
        self.closing, self.last_plot, self.plot_signature = False, 0., None
        self.root.title("P5 WiFi Occupancy Lab V1" + (" — SINTETICO" if self.synthetic else ""))
        # Reserve room for window decorations and the Windows taskbar.
        work_width, work_height = root.winfo_screenwidth(), root.winfo_screenheight()
        try:
            import ctypes
            from ctypes import wintypes
            area = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(area), 0):
                work_width, work_height = area.right-area.left, area.bottom-area.top
        except (AttributeError, OSError):
            work_height -= 48
        width, height = min(1420, work_width-32), min(940, work_height-64)
        self.root.geometry(f"{width}x{height}+16+16")
        self.root.minsize(min(760, width), min(480, height))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        self.root.configure(bg="#eef2f6")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#eef2f6")
        style.configure("TLabel", background="#eef2f6", font=("Segoe UI", 10))
        style.configure("TLabelframe", background="#eef2f6")
        style.configure("TLabelframe.Label", background="#eef2f6", font=("Segoe UI", 10, "bold"))
        style.configure("TButton", padding=(9, 5), font=("Segoe UI", 9))
        style.configure("Accent.TButton", background="#087e8b", foreground="white")
        style.configure("Treeview", rowheight=27, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        header = tk.Frame(root, bg="#142b43", height=78)
        header.grid(row=0,column=0,sticky="ew")
        tk.Label(header, text="P5  /  WiFi Occupancy Lab", bg="#142b43", fg="white",
                 font=("Segoe UI", 21, "bold")).pack(anchor="w", padx=20, pady=(10,0))
        tk.Label(header, text="Universidad de Cuenca · Redes Vehiculares y Heterogéneas · Laboratorio local V1",
                 bg="#142b43", fg="#b9d5df", font=("Segoe UI",10)).pack(anchor="w", padx=21,pady=(0,10))
        banner = "SINTETICO · sin radio, emulación temporal acelerada  |  " if self.synthetic else ""
        warning=tk.Label(root, text=banner + "MODELO NO CALIBRADO  ·  Una dirección no equivale a una persona  ·  Sin fusión de sondas",
                 bg="#fff0cc", fg="#744400", font=("Segoe UI", 10,"bold"), pady=7)
        warning.grid(row=1,column=0,sticky="ew")
        warning.bind('<Configure>',lambda event:warning.configure(wraplength=max(200,event.width-24)))
        body = ttk.Frame(root, padding=10)
        body.grid(row=2,column=0,sticky="nsew")
        self.panes=tk.PanedWindow(body,orient='horizontal',bg='#eef2f6',sashwidth=8,sashrelief='raised',borderwidth=0)
        self.panes.pack(fill='both',expand=True)
        left_host = ttk.Frame(self.panes,width=350)
        self.panes.add(left_host,minsize=240,width=350,stretch='never')
        left,self.sidebar_canvas=self.scrollable(left_host,width=330,min_width=330)
        self.right = ttk.Notebook(self.panes)
        self.right.enable_traversal()
        self.panes.add(self.right,minsize=300,stretch='always')
        self.ports, self.selected, self.device_labels = {}, {}, {}
        self.connect_buttons, self.disconnect_buttons = {}, {}
        self.model_enabled, self.b_values, self.p_values, self.model_labels = {}, {}, {}, {}
        self.form_controls=[]
        for index,sensor in enumerate(SENSORS,1):
            card=ttk.LabelFrame(left,text=f"{probe_label(sensor)}  ·  {BUS_ID}",padding=10)
            card.pack(fill="x",pady=(0,8))
            self.selected[sensor]=tk.BooleanVar(value=index==1)
            self.form_controls.append(ttk.Checkbutton(card,text="Incluir en el experimento",variable=self.selected[sensor]))
            self.form_controls[-1].pack(anchor="w")
            self.ports[sensor]=ttk.Combobox(card,state="readonly",width=30)
            self.ports[sensor].pack(fill="x",pady=5)
            actions=ttk.Frame(card);actions.pack(fill="x")
            self.connect_buttons[sensor]=ttk.Button(actions,text="Conectar / verificar",command=lambda s=sensor:self.connect(s))
            self.connect_buttons[sensor].pack(side="left")
            self.disconnect_buttons[sensor]=ttk.Button(actions,text="Cerrar",command=lambda s=sensor:self.controller.post('disconnect',sensor=s))
            self.disconnect_buttons[sensor].pack(side="left",padx=4)
            label=ttk.Label(card,text="Desconectada",wraplength=300,font=("Segoe UI",9))
            label.pack(anchor="w",pady=5);self.device_labels[sensor]=label
            ttk.Label(card,text="115200 · canal 6 · ventanas 10 s / bloque 120 s",font=("Segoe UI",8)).pack(anchor="w")
            hardware=self.registry.get(sensor,{})
            ttk.Label(card,text=f"{hardware.get('chip','ESP32')} rev {hardware.get('revision','?')} · {hardware.get('usb_bridge','USB/UART')}",font=('Segoe UI',8)).pack(anchor='w')
            self.model_enabled[sensor]=tk.BooleanVar(value=False)
            control=ttk.Checkbutton(card,text="Estimar (NO CALIBRADO)",variable=self.model_enabled[sensor])
            control.pack(anchor="w",pady=(6,1));self.form_controls.append(control)
            fields=ttk.Frame(card);fields.pack(fill="x")
            self.b_values[sensor],self.p_values[sensor]=tk.StringVar(),tk.StringVar()
            for title,var in [("B",self.b_values[sensor]),("pd",self.p_values[sensor])]:
                ttk.Label(fields,text=title).pack(side="left",padx=(0,3))
                entry=ttk.Entry(fields,textvariable=var,width=9);entry.pack(side="left",padx=(0,10))
                self.form_controls.append(entry)
            label=ttk.Label(card,text="Deshabilitado: no se asumen parámetros",wraplength=300,font=("Segoe UI",8))
            label.pack(anchor="w",pady=3);self.model_labels[sensor]=label
        self.refresh_button=ttk.Button(left,text="Actualizar puertos disponibles",command=self.refresh_ports)
        self.refresh_button.pack(fill="x")
        ttk.Label(left,text="Conectar reinicia la placa y verifica autopruebas con radio apagada. No envía START.",wraplength=320,font=("Segoe UI",9)).pack(pady=8,anchor="w")
        features=ttk.LabelFrame(left,text="Funciones pendientes",padding=8);features.pack(fill="x",pady=5)
        self.ap_button=ttk.Button(features,text="AP privado · firmware pendiente",state="disabled");self.ap_button.pack(fill="x")
        self.channel_button=ttk.Button(features,text="Cambiar canal · firmware pendiente",state="disabled");self.channel_button.pack(fill="x",pady=4)
        self._build_experiment()
        self._build_live()
        self._build_history()
        self._build_events()
        self.right.select(self.live_tab)
        self.status=tk.StringVar(value="Sin adquisición. Conecte manualmente una o ambas sondas.")
        self.status_label=ttk.Label(root,textvariable=self.status,anchor="w",padding=(12,6))
        self.status_label.grid(row=3,column=0,sticky="ew")
        self.root.protocol("WM_DELETE_WINDOW",self.close)
        self.refresh_ports()
        self.root.after(100,self.poll)

    def _build_experiment(self):
        container=ttk.Frame(self.right);self.experiment_tab=container;self.right.add(container,text="Experimento")
        tab,self.experiment_canvas=self.scrollable(container,padding=16,min_width=800)
        ttk.Label(tab,text="Definir antes de iniciar",font=("Segoe UI",15,"bold")).grid(row=0,column=0,columnspan=2,sticky="w",pady=(0,12))
        self.variables={key:tk.StringVar(value=value) for key,value in {
            'preset':'P0','mode':'Controlada','duration':'120','phones':'','location':'','distance':'',
            'wifi_state':'No documentado','screen':'No documentado','activity':'','manual_count':''}.items()}
        definitions=[('Plantilla propuesta','preset',list(PRESETS)),('Modalidad','mode',['Controlada','Escenario real']),
            ('Duración activa [s]','duration',None),('Teléfonos (vacío = desconocido)','phones',None),
            ('Ubicación (sin datos personales)','location',None),('Distancia / geometría','distance',None),
            ('Estado WiFi de los teléfonos','wifi_state',['Encendido','Apagado','Mixto','No documentado']),
            ('Estado de pantalla','screen',['Activa','Apagada','Mixto','No documentado']),
            ('Actividad de los teléfonos','activity',None),('Aforo inicial (vacío = no observado)','manual_count',None)]
        for row,(label,key,values) in enumerate(definitions,1):
            ttk.Label(tab,text=label).grid(row=row,column=0,sticky="w",pady=4,padx=(0,14))
            widget=ttk.Combobox(tab,textvariable=self.variables[key],values=values,state='readonly',width=47) if values else ttk.Entry(tab,textvariable=self.variables[key],width=50)
            widget.grid(row=row,column=1,sticky="ew",pady=4);self.form_controls.append(widget)
            if key=='preset':widget.bind('<<ComboboxSelected>>',lambda _:self.preset_description())
        self.preset_text=ttk.Label(tab,text='',wraplength=720,foreground="#33556b")
        self.preset_text.grid(row=11,column=0,columnspan=2,sticky="w",pady=10)
        ttk.Label(tab,text="Observaciones iniciales (sin MAC, SSID ni información personal)").grid(row=12,column=0,columnspan=2,sticky="w")
        self.notes=tk.Text(tab,height=4,width=55,font=("Segoe UI",10),wrap='word');self.notes.grid(row=13,column=0,columnspan=2,sticky='ew',pady=6)
        self.batches=tk.BooleanVar(value=False)
        control=ttk.Checkbutton(tab,text="Autorizar bloques sucesivos de 120 s SOLO dentro de este experimento (duraciones >120 s)",variable=self.batches)
        control.grid(row=14,column=0,columnspan=2,sticky='w',pady=8);self.form_controls.append(control)
        ttk.Label(tab,text="Los parámetros B y pd se fijan por sonda al iniciar. Son supuestos, nunca valores calibrados.\nEl aforo puede actualizarse durante la medición; su referencia es el instante de recepción PC.",wraplength=760).grid(row=15,column=0,columnspan=2,sticky='w',pady=12)
        tab.columnconfigure(1,weight=1)
        self.preset_description()

    def _build_live(self):
        container=ttk.Frame(self.right);self.live_tab=container;self.right.add(container,text="Adquisición")
        tab,self.live_scroll_canvas=self.scrollable(container,padding=8,min_width=900)
        self.authorized=tk.BooleanVar(value=False)
        self.auth_control=ttk.Checkbutton(tab,text="Confirmo entorno autorizado y correspondencia física de las placas para esta medición",variable=self.authorized)
        self.auth_control.pack(anchor='w',pady=3)
        ttk.Label(tab,text="La identidad BUS real se comprueba al primer JSON; antes de START solo hay identidad esperada por puerto/USB.",font=("Segoe UI",8)).pack(anchor='w')
        self.start_hint=ttk.Label(tab,text='Complete la ficha Experimento y conecte las sondas.',foreground='#875300',font=('Segoe UI',8))
        self.start_hint.pack(anchor='w')
        actions=ttk.Frame(tab);actions.pack(fill='x',pady=6)
        self.start_button=ttk.Button(actions,text="Iniciar manualmente",style='Accent.TButton',command=self.start)
        self.start_button.pack(side='left')
        self.pause_button=ttk.Button(actions,text="Pausar",command=lambda:self.controller.post('pause'));self.pause_button.pack(side='left',padx=4)
        self.resume_button=ttk.Button(actions,text="Reanudar",command=lambda:self.controller.post('resume'));self.resume_button.pack(side='left')
        self.stop_button=ttk.Button(actions,text="Detener y cerrar",command=lambda:self.controller.post('stop'));self.stop_button.pack(side='left',padx=4)
        self.clock_label=ttk.Label(actions,text="00:00 / 02:00",font=("Segoe UI",12,'bold'));self.clock_label.pack(side='right')
        self.progress=ttk.Progressbar(tab,maximum=120);self.progress.pack(fill='x',pady=(0,6))
        columns=('sensor','probes','unique','rssi','channel','heap','drops','estimate','manual','error')
        self.metrics=ttk.Treeview(tab,columns=columns,show='headings',height=2)
        names=['Sonda','Probes','Únicos','RSSI med/min/max','Canal','Heap libre','Desc. C/T/B','Est. personas','Aforo','Error abs.']
        for col,title in zip(columns,names):
            self.metrics.heading(col,text=title);self.metrics.column(col,width=76 if col!='rssi' else 135,anchor='center',stretch=True)
        for sensor in SENSORS:self.metrics.insert('', 'end', iid=sensor,values=[probe_label(sensor)]+['—']*9)
        self.metrics.pack(fill='x',pady=5)
        options=ttk.Frame(tab);options.pack(fill='x')
        ttk.Label(options,text='Gráficas:').pack(side='left')
        self.filter=tk.StringVar(value='Ambas')
        ttk.Combobox(options,textvariable=self.filter,values=['Ambas',*PROBE_IDS.values()],state='readonly',width=12).pack(side='left',padx=5)
        self.png_button=ttk.Button(options,text='Exportar PNG',command=self.save_live_png);self.png_button.pack(side='right')
        self.figure=new_figure();self.canvas=FigureCanvasTkAgg(self.figure,master=tab)
        self.canvas.get_tk_widget().pack(fill='both',expand=True)
        self.plot_toolbar=NavigationToolbar2Tk(self.canvas,tab,pack_toolbar=False)
        self.plot_toolbar.pack(fill='x')
        self.live_plot=LivePlot(self.figure,self.provider.data_source);self.canvas.draw_idle()
        self.destination=ttk.Label(tab,text='Datos: aún no se ha creado un experimento',font=("Segoe UI",8),wraplength=950)
        self.destination.pack(anchor='w')

    def _build_history(self):
        container=ttk.Frame(self.right);self.history_tab=container;self.right.add(container,text="Historial")
        tab,self.history_scroll_canvas=self.scrollable(container,padding=10,min_width=1100)
        row=ttk.Frame(tab);row.pack(fill='x');self.history_actions=row
        ttk.Button(row,text='Cargar metadata.json',command=self.browse_history).pack(side='left')
        ttk.Button(row,text='Cargar último experimento',command=self.load_current).pack(side='left',padx=5)
        ttk.Button(row,text='Limpiar comparación',command=self.clear_history).pack(side='left')
        ttk.Button(row,text='Ficha / estadísticas',command=self.history_details).pack(side='left',padx=4)
        ttk.Button(row,text='CSV seleccionado',command=self.save_history_csv).pack(side='right')
        ttk.Button(row,text='PNG comparativo',command=self.save_history_png).pack(side='right',padx=4)
        self.mix_sources=tk.BooleanVar(value=False)
        ttk.Checkbutton(tab,text='Permitir comparación visual real/sintético, manteniendo estadísticas separadas',variable=self.mix_sources).pack(anchor='w',pady=5)
        columns=('experiment','source','condition','sensor','n','mean','std','zero','error')
        self.history_table=ttk.Treeview(tab,columns=columns,show='headings',height=5)
        for key,title in zip(columns,['Experimento','Origen','Condición','Sonda','Ventanas','Media únicos','Desv. muestral','% sin probes','Error abs. medio']):
            self.history_table.heading(key,text=title);self.history_table.column(key,width=100,anchor='center')
        self.history_table.pack(fill='x')
        self.history_notice=ttk.Label(tab,text='Estadísticas por sonda y experimento; no se fusionan ni suman direcciones.',wraplength=850)
        self.history_notice.pack(anchor='w',pady=5)
        self.history_figure=new_figure();self.history_canvas=FigureCanvasTkAgg(self.history_figure,master=tab)
        self.history_canvas.get_tk_widget().pack(fill='both',expand=True)
        draw(self.history_figure,[]);self.history_canvas.draw_idle()

    def _build_events(self):
        container=ttk.Frame(self.right);self.events_tab=container;self.right.add(container,text='Aforo / incidencias')
        tab,self.events_scroll_canvas=self.scrollable(container,padding=10,min_width=650)
        row=ttk.Frame(tab);row.pack(fill='x',pady=5)
        ttk.Label(row,text='Aforo manual actual:').pack(side='left')
        self.manual_value=tk.StringVar()
        ttk.Entry(row,textvariable=self.manual_value,width=12).pack(side='left',padx=6)
        self.manual_button=ttk.Button(row,text='Registrar instante PC',command=self.update_manual);self.manual_button.pack(side='left')
        note=ttk.Frame(tab);note.pack(fill='x',pady=7)
        self.operator_note=tk.StringVar()
        ttk.Entry(note,textvariable=self.operator_note).pack(side='left',fill='x',expand=True)
        self.note_button=ttk.Button(note,text='Añadir observación',command=self.add_note);self.note_button.pack(side='left',padx=5)
        ttk.Label(tab,text='No incluya MAC, SSID ni datos personales. Las incidencias no conservan bytes seriales recibidos.',wraplength=850).pack(anchor='w')
        event_frame=ttk.Frame(tab);event_frame.pack(fill='both',expand=True,pady=10)
        self.events_box=tk.Text(event_frame,state='disabled',wrap='word',font=('Consolas',10),height=23)
        event_scroll=ttk.Scrollbar(event_frame,orient='vertical',command=self.events_box.yview)
        self.events_box.configure(yscrollcommand=event_scroll.set)
        event_scroll.pack(side='right',fill='y');self.events_box.pack(side='left',fill='both',expand=True)

    def preset_description(self):
        code=self.variables['preset'].get();title,description=PRESETS[code]
        self.preset_text.configure(text=f'{code} · {title}: {description}  [Plantilla propuesta V1, editable]')

    def scrollable(self,parent,padding=0,width=None,min_width=0):
        parent.rowconfigure(0,weight=1);parent.columnconfigure(0,weight=1)
        canvas=tk.Canvas(parent,bg='#eef2f6',highlightthickness=0,**({'width':width} if width else {}))
        scrollbar=ttk.Scrollbar(parent,orient='vertical',command=canvas.yview)
        horizontal=ttk.Scrollbar(parent,orient='horizontal',command=canvas.xview)
        scrollbar.grid(row=0,column=1,sticky='ns');horizontal.grid(row=1,column=0,sticky='ew')
        canvas.grid(row=0,column=0,sticky='nsew')
        canvas.configure(yscrollcommand=scrollbar.set,xscrollcommand=horizontal.set,yscrollincrement=24,xscrollincrement=24)
        inner=ttk.Frame(canvas,padding=padding)
        item=canvas.create_window((0,0),window=inner,anchor='nw')
        inner.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda event:canvas.itemconfigure(item,width=max(min_width,event.width)))
        def wheel(event):
            widget=event.widget
            if isinstance(widget,tk.Text) and widget.yview()!=(0.,1.):return
            while widget is not None:
                if widget is inner or widget is canvas:
                    delta=-1 if event.delta>0 else 1
                    (canvas.xview_scroll if event.state & 1 else canvas.yview_scroll)(delta*3,'units')
                    return 'break'
                widget=getattr(widget,'master',None)
        # Run before widget class bindings (not after Combobox changes its value).
        tag=f'LabScroll{str(canvas)}'
        canvas.bind_class(tag,'<MouseWheel>',wheel)
        def bind_children():
            def attach(widget):
                widget.bindtags((tag,*[t for t in widget.bindtags() if t!=tag]))
                for child in widget.winfo_children():attach(child)
            attach(canvas)
        parent.after_idle(bind_children)
        return inner,canvas

    def refresh_ports(self):
        try:
            ports=self.provider.ports()
            names=[p['port'] for p in ports]
            for sensor,widget in self.ports.items():
                current=widget.get();widget['values']=names
                matching=[p['port'] for p in ports if (p['vid'],p['pid'])==((0x1A86,0x7523) if sensor=='BUS_001' else (0x10C4,0xEA60))]
                if current not in names:widget.set(matching[0] if len(matching)==1 else '')
        except Exception:
            self.error('No se pudo enumerar puertos; no se abrió ninguna placa')

    def connect(self,sensor):
        port=self.ports[sensor].get()
        if not port:self.error('Seleccione un puerto presente');return
        self.controller.post('connect',sensor=sensor,port=port)

    def build_plan(self):
        values={key:var.get() for key,var in self.variables.items()}
        params={sensor:Parameters(number(self.b_values[sensor].get()),number(self.p_values[sensor].get()))
                if self.model_enabled[sensor].get() and self.selected[sensor].get() else None for sensor in SENSORS}
        return Plan(values['preset'],values['mode'],number(values['duration']),optional_count(values['phones']),
            values['location'],values['distance'],values['wifi_state'],values['screen'],values['activity'],
            self.notes.get('1.0','end').strip(),optional_count(values['manual_count']),params,self.batches.get()).validate()

    def start(self):
        try:
            plan=self.build_plan()
            sensors=[s for s in SENSORS if self.selected[s].get()]
            if not self.synthetic and not self.authorized.get():
                raise ValueError('Confirme entorno autorizado y correspondencia física antes de START')
            self.controller.post('start',plan=plan,sensors=sensors,authorized=self.authorized.get())
            self.authorized.set(False)  # confirmation is not silently reused for a new experiment
        except (ValueError,OverflowError):
            self.error('Revise los parámetros: ubicación/distancia/actividad, duración, cantidades, B >= 0 y 0 < pd <= 1. Confirme también el entorno autorizado.')

    def update_manual(self):
        try:
            count=int(self.manual_value.get())
            if count<0:raise ValueError()
            self.controller.post('manual',count=count)
        except ValueError:self.error('El aforo manual debe ser un entero >= 0')

    def add_note(self):
        self.controller.post('note',text=private_text(self.operator_note.get()))
        self.operator_note.set('')

    def error(self,text):
        messagebox.showerror('P5 Lab',text,parent=self.root)

    def poll(self):
        if self.closing:
            if not self.controller.thread.is_alive():
                self.root.destroy();return
            self.root.after(100,self.poll);return
        snapshot=self.controller.snapshot();state=snapshot['state'];active=state in ACTIVE
        selected=[s for s in SENSORS if self.selected[s].get()]
        self.status.set(f"{state}  ·  {snapshot['reason']}" if snapshot['reason'] else f"{state} · Datos {snapshot['source']} · No hay captura fuera de un experimento iniciado manualmente")
        for widget in self.form_controls:
            widget.configure(state='disabled' if active else 'readonly' if isinstance(widget,ttk.Combobox) else 'normal')
        self.notes.configure(state='disabled' if active else 'normal')
        self.refresh_button.configure(state='disabled' if active else 'normal')
        self.auth_control.configure(state='disabled' if active or self.synthetic else 'normal')
        for sensor in SENSORS:
            device=snapshot['devices'][sensor]
            self.connect_buttons[sensor].configure(state='disabled' if active or sensor in self.controller.workers else 'normal')
            self.disconnect_buttons[sensor].configure(state='normal' if sensor in self.controller.workers else 'disabled')
            self.ports[sensor].configure(state='disabled' if active or sensor in self.controller.workers else 'readonly')
            self.device_labels[sensor].configure(text=device['status']+f"\nID {'verificado' if device['identity_verified'] else 'pendiente'} · Canal efectivo: {fmt(device['channel_effective'])}")
            if self.model_enabled[sensor].get():
                try:
                    Parameters(number(self.b_values[sensor].get()),number(self.p_values[sensor].get()))
                    self.model_labels[sensor].configure(text='Supuestos válidos · NO CALIBRADO',foreground='#875300')
                except (ValueError,OverflowError):self.model_labels[sensor].configure(text='B/pd inválidos: estimación deshabilitada',foreground='#b91c1c')
            else:self.model_labels[sensor].configure(text='Deshabilitado: parámetros no asumidos',foreground='#33556b')
            row=device['latest']
            if row:
                self.metrics.item(sensor,values=[probe_label(sensor),row['probe_requests'],row['unique_addresses'],
                    '/'.join(fmt(row[k]) for k in ['rssi_mean_dbm','rssi_min_dbm','rssi_max_dbm']),row['channel'],row['free_heap_bytes'],
                    f"{row['dropped_events']}/{row['unique_overflow_events']}/{row['boundary_rejected_events']}",fmt(row['estimated_people']),fmt(row['manual_count']),fmt(row['absolute_error'])])
            else:self.metrics.item(sensor,values=[probe_label(sensor)]+['—']*9)
        can_start=not active and bool(selected) and all(snapshot['devices'][s]['ready'] for s in selected)
        hint='Listo para inicio manual; parámetros asumidos NO CALIBRADOS.'
        try:self.build_plan()
        except (ValueError,OverflowError):
            can_start=False;hint='Complete Experimento (ubicación/distancia/actividad/cantidades) y valide B/pd si solicita estimación.'
        if not selected:hint='Seleccione al menos una sonda para incluir en el experimento.'
        elif not all(snapshot['devices'][s]['ready'] for s in selected) and not active:hint='Conecte las sondas seleccionadas y espere las 19 autopruebas sin radio.'
        if not self.synthetic and not self.authorized.get() and not active:
            can_start=False;hint+=' Confirme un entorno autorizado para esta medición.'
        if active:hint='Medición en curso: pausas y cambios de aforo quedan registrados; ante error se aborta sin rellenar datos.'
        self.start_hint.configure(text=hint)
        self.start_button.configure(state='normal' if can_start else 'disabled')
        self.pause_button.configure(state='normal' if state=='RECORDING' else 'disabled')
        self.resume_button.configure(state='normal' if state=='PAUSED' else 'disabled')
        self.stop_button.configure(state='normal' if active else 'disabled')
        self.manual_button.configure(state='normal' if active else 'disabled');self.note_button.configure(state='normal' if active else 'disabled')
        self.png_button.configure(state='disabled' if active else 'normal')
        for button in self.history_actions.winfo_children():button.configure(state='disabled' if active else 'normal')
        elapsed,duration=snapshot['elapsed'],snapshot['duration']
        self.clock_label.configure(text=f'{int(elapsed)//60:02}:{int(elapsed)%60:02} / {int(duration)//60:02}:{int(duration)%60:02}')
        self.progress.configure(maximum=duration,value=min(elapsed,duration))
        if snapshot['path']:self.destination.configure(text='Guardado automático: '+snapshot['path'])
        signature=(tuple(rows[-1]['host_monotonic_ns'] if rows else 0 for rows in snapshot['samples'].values()),len(snapshot['manual']),self.filter.get(),snapshot['path'])
        if signature!=self.plot_signature and time.monotonic()-self.last_plot>1:
            origin=self.controller.origin
            manual=[((stamp-origin)/1e9,count) for stamp,count in snapshot['manual']]
            self.live_plot.update(snapshot['samples'],manual,self.filter.get())
            self.canvas.draw_idle();self.last_plot=time.monotonic();self.plot_signature=signature
        text='\n'.join(f"{event['time']}  {event['code']}  {json.dumps(event['detail'],ensure_ascii=False)}" for event in snapshot['events'])
        if getattr(self,'_event_text',None)!=text:
            self.events_box.configure(state='normal');self.events_box.delete('1.0','end');self.events_box.insert('end',text)
            self.events_box.see('end');self.events_box.configure(state='disabled');self._event_text=text
        if not active:self._poll_history()
        self.root.after(200,self.poll)

    def browse_history(self):
        path=filedialog.askopenfilename(parent=self.root,title='Experimento del laboratorio',initialdir=self.project/'data',filetypes=[('Metadatos','metadata.json')])
        if path:self.load_path(path)

    def load_current(self):
        snapshot=self.controller.snapshot()
        if snapshot['state'] in ACTIVE:self.error('Detenga el experimento antes de cargarlo en historial');return
        if snapshot['path']:self.load_path(snapshot['path'])

    def load_path(self,path):
        def read():
            try:self.history_queue.put(('dataset',load_experiment(path)))
            except Exception:self.history_queue.put(('error','No se pudo validar el experimento; requiere metadata.json y JSONL del laboratorio'))
        threading.Thread(target=read,daemon=True).start()

    def _poll_history(self):
        try:kind,data=self.history_queue.get_nowait()
        except queue.Empty:return
        if kind=='error':self.error(data);return
        if len(self.history)>=4:self.error('Compare hasta cuatro experimentos a la vez; limpie la comparación para cargar otros');return
        if any(d['path']==data['path'] for d in self.history):return
        if self.history and not self.mix_sources.get() and data['metadata']['data_source']!=self.history[0]['metadata']['data_source']:
            self.error('No se mezclan fuentes reales y sintéticas por defecto');return
        self.history.append(data);self.redraw_history()

    def redraw_history(self):
        self.history_table.delete(*self.history_table.get_children())
        datasets=[];warnings=[];manual_series={}
        for index,data in enumerate(self.history):
            meta=data['metadata'];condition=meta['plan']['preset']+' / '+meta['plan']['mode']
            for sensor,stats in data['statistics'].items():
                self.history_table.insert('', 'end',iid=f'{index}:{sensor}',values=[meta['experiment_id'][-10:]+' / '+meta['status'],meta['data_source'],condition,probe_label(sensor),
                    stats['windows'],fmt(stats['unique_addresses']['mean']),fmt(stats['unique_addresses']['sample_stddev']),
                    fmt(stats['percent_windows_without_probes']),fmt(stats['absolute_error']['mean'])])
            label=f"{condition} · {meta['data_source']} · {meta['experiment_id'][-6:]}"
            datasets.append((label,data['rows']));manual_series[label]=data['manual']
            warnings.extend(data['warnings'])
        self.history_notice.configure(text='; '.join(warnings) if warnings else 'Comparación relativa por tiempo PC de cada experimento. Sin fusión; ventanas sin probes no equivalen a buses vacíos.')
        draw(self.history_figure,datasets,manual_by_dataset=manual_series);self.history_canvas.draw_idle()

    def history_details(self):
        selection=self.history_table.selection()
        if not selection:self.error('Seleccione una fila de experimento');return
        data=self.history[int(selection[0].split(':')[0])]
        window=tk.Toplevel(self.root);window.title('Ficha y estadísticas · NO CALIBRADO');window.geometry('820x600')
        text=tk.Text(window,wrap='word',font=('Consolas',10));text.pack(fill='both',expand=True)
        detail={'metadata':data['metadata'],'statistics_per_sensor':data['statistics'],'warnings':data['warnings']}
        text.insert('1.0',private_text(json.dumps(detail,indent=2,ensure_ascii=False)) if len(str(detail))<2000 else json.dumps(detail,indent=2,ensure_ascii=False))
        text.configure(state='disabled')

    def clear_history(self):
        self.history=[];self.redraw_history()

    def _export_path(self,extension):
        folder=self.project/'data/processed/lab_exports';folder.mkdir(exist_ok=True,parents=True)
        destination=filedialog.asksaveasfilename(parent=self.root,initialdir=folder,defaultextension=extension,filetypes=[(extension, '*'+extension)])
        if not destination:return None
        if Path(destination).exists():self.error('Elija un nombre nuevo; se conservan los archivos existentes');return None
        return destination

    def save_live_png(self):
        path=self._export_path('.png')
        if path:self.figure.savefig(path,dpi=150)

    def save_history_png(self):
        path=self._export_path('.png')
        if path:self.history_figure.savefig(path,dpi=150)

    def save_history_csv(self):
        selection=self.history_table.selection()
        if not selection:self.error('Seleccione una fila del experimento a exportar');return
        index=int(selection[0].split(':')[0]);path=self._export_path('.csv')
        if path:export_csv(self.history[index],path)

    def close(self):
        self.closing=True
        self.status.set('Deteniendo y cerrando puertos; no desconecte la aplicación durante el cierre…')
        self.controller.post('shutdown')
