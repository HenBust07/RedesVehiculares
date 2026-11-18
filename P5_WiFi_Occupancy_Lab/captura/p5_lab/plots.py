"""Graficas comparativas con reloj PC; segmentos separados por NaN, nunca ceros."""
import math
from matplotlib.figure import Figure
from .model import MODEL_STATUS
from .identity import BUS_ID, probe_label

COLORS = {"BUS_001": "#087e8b", "BUS_002": "#8a4fba"}


def new_figure():
    return Figure(figsize=(9, 5.8), dpi=100, layout="constrained", facecolor="#f8fafc")


def draw(figure, datasets, *, sensor_filter="Ambas", manual=None, manual_by_dataset=None):
    figure.clear()
    axes = figure.subplots(2, 2)
    specifications = [("probe_requests", "Probe Requests por ventana", axes[0, 0]),
                      ("unique_addresses", "Direcciones unicas por ventana (no personas)", axes[0, 1]),
                      ("rssi_mean_dbm", "RSSI medio y rango [dBm]", axes[1, 0]),
                      ("estimated_people", "Personas estimadas / aforo manual — NO CALIBRADO", axes[1, 1])]
    for dataset_index, (label, rows) in enumerate(datasets):
        for sensor, color in COLORS.items():
            if sensor_filter not in ("Ambas", sensor, probe_label(sensor)):
                continue
            selected = [row for row in rows if row["sensor_id"] == sensor]
            if not selected:
                continue
            for key, _, axis in specifications:
                xs, ys, lower, upper = [], [], [], []
                previous = None
                for row in selected[-720:]:
                    if previous is not None and row["segment_id"] != previous:
                        xs.append(math.nan); ys.append(math.nan); lower.append(math.nan); upper.append(math.nan)
                    xs.append(row["host_elapsed_s"])
                    ys.append(row[key] if row[key] is not None else math.nan)
                    lower.append(row["rssi_min_dbm"] if row["rssi_min_dbm"] is not None else math.nan)
                    upper.append(row["rssi_max_dbm"] if row["rssi_max_dbm"] is not None else math.nan)
                    previous = row["segment_id"]
                axis.plot(xs, ys, color=color, linestyle=('-', '--', '-.', ':')[dataset_index % 4], marker=".",
                          markersize=4, linewidth=1.3, label=f"{label} · {probe_label(sensor)}")
                if key == "rssi_mean_dbm":
                    axis.fill_between(xs, lower, upper, color=color, alpha=.12)
        # Saved manual references, per experiment; never sum per-sensor references.
        by_time = {}
        for row in rows:
            if row.get("manual_count") is not None:
                by_time[row["host_elapsed_s"]] = row["manual_count"]
        if manual_by_dataset is not None and manual_by_dataset.get(label):
            timeline=list(manual_by_dataset[label])
            horizon=max((r['host_elapsed_s'] for r in rows),default=timeline[-1][0])
            if horizon>timeline[-1][0]:timeline.append((horizon,timeline[-1][1]))
            axes[1,1].step([p[0] for p in timeline],[p[1] for p in timeline],where='post',
                          color='#4b5563',linestyle=':' if dataset_index else '--',label=f'{label} · último aforo observado')
        elif by_time and manual is None:
            times = sorted(by_time)
            axes[1, 1].step(times, [by_time[t] for t in times], where="post", color="#4b5563",
                            linestyle=":" if dataset_index else "--", label=f"{label} · aforo al recibir PC")
    if manual:
        axes[1, 1].step([p[0] for p in manual], [p[1] for p in manual], where="post", color="#263238", linestyle="--", label="Aforo manual (instantes PC)")
    for _, title, axis in specifications:
        axis.set_title(title, fontsize=9)
        axis.set_xlabel("Tiempo PC desde inicio [s], incluye pausas", fontsize=8)
        axis.tick_params(labelsize=8)
        axis.grid(alpha=.2)
        handles, _ = axis.get_legend_handles_labels()
        if handles:
            axis.legend(fontsize=6, loc="best")
    figure.suptitle(f"P5 WiFi Occupancy Lab · {MODEL_STATUS} · sin fusion de sondas", fontsize=11)
    return figure


class LivePlot:
    """Reutiliza artistas: evita reconstruir cuatro ejes en cada muestra."""
    def __init__(self,figure,source='real'):
        self.figure=draw(figure,[])
        # Live axes have a fixed topology: avoid an expensive constrained-layout solve on every frame.
        self.figure.set_layout_engine(None)
        self.figure.subplots_adjust(left=.09,right=.98,bottom=.13,top=.85,wspace=.28,hspace=.78)
        label='SINTÉTICO' if source=='synthetic' else 'REAL'
        self.figure.suptitle(f'P5 WiFi Occupancy Lab · {BUS_ID} · {label} · NO CALIBRADO · sin fusión',fontsize=11)
        self.axes=figure.axes
        self.lines={}
        for sensor,color in COLORS.items():
            self.lines[sensor]=[axis.plot([],[],color=color,marker='.',markersize=4,linewidth=1.2,label=probe_label(sensor))[0] for axis in self.axes]
            for style in (':','--'):
                self.lines[sensor].append(self.axes[2].plot([],[],color=color,linestyle=style,alpha=.5,linewidth=.8)[0])
        self.manual_line=self.axes[3].step([],[],where='post',color='#263238',linestyle='--',label='Último aforo manual observado')[0]
        for axis in self.axes:axis.legend(fontsize=6,loc='best')
        self.empty_model=self.axes[3].text(.5,.5,'Sin estimación habilitada',transform=self.axes[3].transAxes,
                                         ha='center',color='#64748b',fontsize=9)

    def update(self,samples,manual,sensor_filter='Ambas'):
        has_estimate=False
        keys=['probe_requests','unique_addresses','rssi_mean_dbm','estimated_people','rssi_min_dbm','rssi_max_dbm']
        for sensor,lines in self.lines.items():
            rows=list(samples[sensor])[-720:]
            visible=sensor_filter in ('Ambas',sensor,probe_label(sensor))
            for key,line in zip(keys,lines):
                xs,ys=[],[];previous=None
                for row in rows:
                    if previous is not None and row['segment_id']!=previous:
                        xs.append(math.nan);ys.append(math.nan)
                    xs.append(row['host_elapsed_s']);ys.append(row[key] if row[key] is not None else math.nan)
                    previous=row['segment_id']
                line.set_data(xs,ys);line.set_visible(visible)
            has_estimate=has_estimate or (visible and any(r['estimated_people'] is not None for r in rows))
        timeline=list(manual)
        horizon=max((r['host_elapsed_s'] for rows in samples.values() for r in rows),default=0)
        if timeline and horizon>timeline[-1][0]:timeline.append((horizon,timeline[-1][1]))
        self.manual_line.set_data([p[0] for p in timeline],[p[1] for p in timeline])
        self.empty_model.set_visible(not has_estimate and not manual)
        for axis in self.axes:
            axis.relim(visible_only=True);axis.autoscale_view()
