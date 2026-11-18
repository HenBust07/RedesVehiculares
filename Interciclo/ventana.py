import tkinter as tk
from tkinter import ttk, messagebox
from modelo import EstadoBus, DATOS_DEMO, recomendar, buses_para_parada
from visor import VisorSimulacion
from configuracion import PARADAS, INTERVALO_PANTALLA_MS
from simulacion import Simulacion


class Ventana(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('¡Viene a full!!! | Línea 3')
        self.geometry('1150x730')
        self.minsize(850, 600)
        self.configure(bg='#f1f5f9')
        self.parada = tk.StringVar(value='P1')
        self.simulacion = Simulacion()
        self.en_ejecucion = False   
        self.tarea = None
        self.bus_mostrado = None
        self._crear_interfaz()
        self.actualizar()
        self.protocol('WM_DELETE_WINDOW', self.salir)

    def _crear_interfaz(self):
        raiz = tk.Frame(self, bg='#f1f5f9')
        raiz.pack(fill='both', expand=True, padx=16, pady=16)
        raiz.grid_columnconfigure(0, weight=1, minsize=290)
        raiz.grid_columnconfigure(1, weight=2, minsize=470)
        raiz.grid_rowconfigure(0, weight=1)
        izq = tk.Frame(raiz, bg='white', padx=18, pady=12)
        izq.grid(row=0, column=0, sticky='nsew', padx=(0, 12))
        der = tk.Frame(raiz, bg='white', padx=14, pady=12)
        der.grid(row=0, column=1, sticky='nsew')
        tk.Label(izq, text='¡Viene a full!!!', font=('Arial', 24, 'bold italic'), bg='white', fg='#172554').pack(pady=(10, 0))
        tk.Label(izq, text='────────  🚌  ────────', bg='white', fg='#2563eb', font=('Arial', 14)).pack()
        tk.Label(izq, text='Línea 3', font=('Arial', 18, 'bold'), bg='white').pack(pady=(18, 4))
        self.bus = tk.Canvas(izq, height=165, bg='white', highlightthickness=0)
        self.bus.pack(fill='x')
        self.bus.bind('<Configure>', lambda e: self.dibujar_bus())
        tk.Label(izq, text='⚪ Blanco: vacío       🔴 Rojo: lleno', bg='white', font=('Arial', 10)).pack(pady=(2, 18))
        # Un solo panel: datos del próximo bus y recomendación.
        cuadro = tk.LabelFrame(
            izq, text='Información', bg='white',
            font=('Arial', 13, 'bold'), padx=12, pady=10
        )
        cuadro.pack(fill='x', pady=(8, 0))

        self.lbl_parada = tk.Label(
            cuadro, bg='white', font=('Arial', 11, 'bold'),
            anchor='w', justify='left'
        )
        self.lbl_parada.pack(fill='x', anchor='w')
        self.lbl_bus = tk.Label(cuadro, bg='white', font=('Arial', 11), anchor='w')
        self.lbl_bus.pack(fill='x', pady=(7, 0))
        self.lbl_capacidad = tk.Label(cuadro, bg='white', font=('Arial', 11), anchor='w')
        self.lbl_capacidad.pack(fill='x', pady=(7, 5))

        self.estilo = ttk.Style(self)
        self.estilo.configure(
            'Ocupacion.Horizontal.TProgressbar',
            troughcolor='#e5e7eb', background='#16a34a'
        )
        self.progreso = ttk.Progressbar(
            cuadro, maximum=100, style='Ocupacion.Horizontal.TProgressbar'
        )
        self.progreso.pack(fill='x')

        self.lbl_llegada = tk.Label(cuadro, bg='white', font=('Arial', 11), anchor='w')
        self.lbl_llegada.pack(fill='x', pady=(9, 4))
        self.lbl_siguientes = tk.Label(
            cuadro, bg='white', font=('Arial', 10), anchor='w', justify='left'
        )
        self.lbl_siguientes.pack(fill='x')

        tk.Frame(cuadro, bg='#cbd5e1', height=1).pack(fill='x', pady=(12, 9))
        tk.Label(
            cuadro, text='Recomendación', bg='white', fg='#172554',
            font=('Arial', 11, 'bold'), anchor='w'
        ).pack(fill='x', pady=(0, 5))

        self.lbl_recomendacion = tk.Label(
            cuadro, bg='#eff6ff', fg='#1e3a8a',
            font=('Arial', 10), justify='left', anchor='w',
            padx=10, pady=8, relief='solid', bd=1,
            wraplength=300
        )
        self.lbl_recomendacion.pack(fill='x')
        # Ajustar el texto al ancho del panel, no al tamaño del propio label.
        cuadro.bind('<Configure>', self._ajustar_recomendacion)
        barra = tk.Frame(der, bg='white')
        barra.pack(fill='x', pady=(0, 12))
        tk.Label(barra, text='Simulación SUMO', bg='white', font=('Arial', 16, 'bold')).pack(side='left')
        tk.Button(barra, text='Salir', command=self.salir, bg='#e2e8f0', relief='flat', padx=14, pady=7).pack(side='right', padx=(8, 0))
        self.btn_simular = tk.Button(barra, text='▶ Simular', command=self.simular, bg='#2563eb', fg='white', relief='flat', padx=14, pady=7)
        self.btn_simular.pack(side='right')
        self.visor = VisorSimulacion(der)
        self.visor.pack(fill='both', expand=True)
        tk.Label(der, text='Selecciona una parada:', bg='white', anchor='w', font=('Arial', 11)).pack(fill='x', pady=(14, 5))
        opciones = tk.Frame(der, bg='white')
        opciones.pack(fill='x')
        for p in PARADAS:
            tk.Radiobutton(opciones, text=p, variable=self.parada, value=p, command=self.actualizar, indicatoron=False,
                           bg='#e2e8f0', selectcolor='#93c5fd', relief='flat', font=('Arial', 13, 'bold'), pady=12).pack(side='left', fill='x', expand=True, padx=4)
        self.estado = tk.Label(der, text='Esperando conexión SUMO · datos demo', bg='white', fg='#64748b', anchor='w')
        self.estado.pack(fill='x', pady=(8, 0))

    def _ajustar_recomendacion(self, event):
        # Evita el bucle de redimensionamiento del widget de recomendación.
        ancho = max(140, event.width - 48)
        if int(self.lbl_recomendacion.cget('wraplength')) != ancho:
            self.lbl_recomendacion.configure(wraplength=ancho)

    def _mostrar_recomendacion(self, mensaje, ocupacion=None):
        """Muestra solo la recomendación, sin encabezados en mayúsculas."""
        if ocupacion is None:
            fondo, texto, borde = '#eff6ff', '#1e3a8a', '#93c5fd'
        elif ocupacion >= 0.9:
            fondo, texto, borde = '#fee2e2', '#991b1b', '#ef4444'
        elif ocupacion >= 0.7:
            fondo, texto, borde = '#fef3c7', '#92400e', '#f59e0b'
        else:
            fondo, texto, borde = '#dcfce7', '#166534', '#4ade80'

        self.lbl_recomendacion.config(
            text=mensaje,
            bg=fondo,
            fg=texto,
            highlightthickness=1,
            highlightbackground=borde,
        )

    def _actualizar_barra(self, porcentaje):
        self.progreso['value'] = porcentaje
        color = '#dc2626' if porcentaje >= 80 else '#f59e0b' if porcentaje >= 50 else '#16a34a'
        self.estilo.configure('Ocupacion.Horizontal.TProgressbar', background=color)

    def dibujar_bus(self):
        """Bus tipo Cuenca: trasera blanca, frente rojo, franja bajo las ventanas."""
        c = self.bus
        c.delete('all')
        w, h = c.winfo_width(), c.winfo_height()
        if w < 100 or h < 100:
            return
        # Diseño proporcional: 560 x 170 unidades, sin depender de imágenes externas.
        escala = min((w - 12) / 560, (h - 8) / 170)
        ox = (w - 560 * escala) / 2
        oy = (h - 170 * escala) / 2
        def pt(x, y): return (ox + x * escala, oy + y * escala)
        def poly(coords, **kw):
            xy = []
            for x, y in coords: xy.extend(pt(x, y))
            return c.create_polygon(*xy, **kw)
        def rect(x1, y1, x2, y2, **kw): return c.create_rectangle(*pt(x1,y1), *pt(x2,y2), **kw)
        def oval(x1, y1, x2, y2, **kw): return c.create_oval(*pt(x1,y1), *pt(x2,y2), **kw)
        e = self.bus_mostrado
        f = max(0, min(1, e['ocupacion'] / max(1, e['capacidad_maxima']))) if e else 0
        # La ocupación hace avanzar el rojo desde el frente hacia la parte trasera.
        corte = 330 - 270 * f
        poly([(22,36),(36,22),(490,22),(520,32),(538,52),(538,125),(22,125)],
             fill='#ffffff', outline='#334155', width=2)
        poly([(corte,23),(490,23),(520,32),(538,52),(538,124),(corte+38,124)],
             fill='#dc2626', outline='')
        # Ventanas oscuras continuas, sin franja diagonal encima.
        poly([(42,39),(479,39),(502,48),(503,77),(38,77),(38,51)],
             fill='#17212b', outline='#0f172a', width=2)
        for x in (98,157,216,275,334,393,451):
            rect(x,41,x+3,76,fill='#64748b',outline='')
        rect(42,44,477,47,fill='#475569',outline='')
        # Franja gris únicamente debajo de la línea de ventanas (y > 78).
        poly([(corte+10,79),(corte+30,79),(corte+67,124),(corte+46,124)],
             fill='#9ca3af',outline='')
        # Puerta delantera y parabrisas.
        poly([(506,48),(521,53),(524,102),(507,102)], fill='#334155',outline='#111827')
        rect(510,57,520,91,fill='#64748b',outline='')
        rect(533,99,539,110,fill='#fbbf24',outline='')
        rect(24,95,29,107,fill='#f59e0b',outline='')
        # Ruedas y detalles.
        for x in (132,458):
            oval(x-24,104,x+24,152,fill='#111827',outline='#374151',width=2)
            oval(x-14,114,x+14,142,fill='#94a3b8',outline='#e2e8f0',width=2)
            oval(x-5,123,x+5,133,fill='#475569',outline='')
        rect(30,121,528,125,fill='#475569',outline='')
        rect(245,111,258,115,fill='#f59e0b',outline='')

    def actualizar(self):
        p = self.parada.get()
        self.lbl_parada.config(text=f'Parada: {p} — {PARADAS[p]["nombre"]}')
        self.visor.seleccionar(p)
        if not self.simulacion.conectada:
            e = DATOS_DEMO[p]
            self.bus_mostrado = {'ocupacion': e.ocupacion, 'capacidad_maxima': e.capacidad_maxima}
            self.lbl_bus.config(text='Datos ficticios (sin SUMO)')
            self.lbl_capacidad.config(text=f'Ocupación: {e.ocupacion}/{e.capacidad_maxima} pasajeros')
            self._actualizar_barra(100 * e.ocupacion / e.capacidad_maxima)
            self.lbl_llegada.config(text=f'Llegada estimada (demo): {e.llegada_min:g} min')
            self.lbl_siguientes.config(text='')
            self._mostrar_recomendacion(recomendar(e), e.ocupacion/max(1,e.capacidad_maxima))
        else:
            candidatos = buses_para_parada(self.simulacion.buses, p)
            self.bus_mostrado = candidatos[0] if candidatos else None
            if candidatos:
                b = candidatos[0]
                porcentaje = 100*b['ocupacion']/max(1,b['capacidad_maxima'])
                self.lbl_bus.config(text=f'Próximo: {b["id"]}')
                self.lbl_capacidad.config(text=f'Ocupación: {b["ocupacion"]}/{b["capacidad_maxima"]} ({porcentaje:.0f} %)')
                self._actualizar_barra(porcentaje)
                self.lbl_llegada.config(text=f'Llegada estimada: {b["eta"][p]:.1f} min')
                siguientes = ', '.join(f'{b["id"]} ({b["eta"][p]:.1f} min)' for b in candidatos[1:4])
                self.lbl_siguientes.config(text='Siguientes: '+siguientes if siguientes else 'No hay otros buses activos en camino')
                self._mostrar_recomendacion(recomendar(EstadoBus(b['ocupacion'], b['capacidad_maxima'], b['eta'][p])), porcentaje/100)
            else:
                self.lbl_bus.config(text='Sin buses activos pendientes de esta parada')
                self.lbl_capacidad.config(text='Ocupación: —')
                self._actualizar_barra(0)
                self.lbl_llegada.config(text='Llegada estimada: —')
                self.lbl_siguientes.config(text='Puede haber buses programados que aún no han salido.')
                self._mostrar_recomendacion('Espera al próximo bus programado.')
        self.dibujar_bus()

    def simular(self):
        if self.en_ejecucion:
            return
        try:
            self.simulacion.conectar()
        except Exception as exc:
            messagebox.showerror('Error de conexión TraCI',
                                 f'No se pudo conectar a SUMO en 127.0.0.1:3400.\n\n{exc}\n\nInicia SUMO con --remote-port 3400.')
            return
        self.en_ejecucion = True
        self.btn_simular.config(state='disabled')
        self._paso()

    def _paso(self):
        if not self.en_ejecucion:
            return
        try:
            self.simulacion.avanzar()
            self.visor.actualizar_buses(self.simulacion.buses)
            self.actualizar()
            self.estado.config(text=f'Tiempo SUMO: {self.simulacion.tiempo:.0f} s · Buses activos: {len(self.simulacion.buses)} · Ocupación real TraCI · Dos puertas' + (f' · Avisos: {len(self.simulacion.avisos)}' if self.simulacion.avisos else ''))
            if self.simulacion.terminada:
                self.en_ejecucion = False
                self.btn_simular.config(state='disabled')
                self.estado.config(text=f'Simulación finalizada en t={self.simulacion.tiempo:.0f} s. Reinicia SUMO para otra prueba.')
                self.simulacion.cerrar()
                return
            self.tarea = self.after(INTERVALO_PANTALLA_MS, self._paso)
        except Exception as exc:
            self.en_ejecucion = False
            self.btn_simular.config(state='disabled')
            self.estado.config(text='Error durante la simulación')
            messagebox.showerror('Error TraCI', str(exc))
            self.simulacion.cerrar()

    def salir(self):
        self.en_ejecucion = False
        if self.tarea is not None:
            self.after_cancel(self.tarea)
            self.tarea = None
        self.simulacion.cerrar()
        self.destroy()


if __name__ == '__main__':
    Ventana().mainloop()