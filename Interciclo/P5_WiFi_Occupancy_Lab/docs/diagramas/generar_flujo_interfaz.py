"""Figura documental; no abre puertos ni ejecuta capturas. Reutiliza Matplotlib."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon


def main():
    output=Path(__file__).resolve().parent
    plt.rcParams.update({'font.family':'DejaVu Sans','svg.fonttype':'none'})
    fig,ax=plt.subplots(figsize=(12,15))
    fig.subplots_adjust(left=.02,right=.98,bottom=.02,top=.98)
    ax.set(xlim=(0,12),ylim=(0,15));ax.axis('off')
    ink='#16324b';teal='#087e8b';muted='#52677a'

    def box(x,y,w,h,text,fill='#eef5fa',edge=ink,size=11):
        ax.add_patch(FancyBboxPatch((x-w/2,y-h/2),w,h,
            boxstyle='round,pad=0.05,rounding_size=0.12',facecolor=fill,edgecolor=edge,linewidth=1.4))
        ax.text(x,y,text,ha='center',va='center',fontsize=size,color=ink,linespacing=1.5)

    def diamond(x,y,w,h,text):
        ax.add_patch(Polygon([(x,y+h/2),(x+w/2,y),(x,y-h/2),(x-w/2,y)],
            facecolor='#fff2ce',edgecolor=ink,linewidth=1.4))
        ax.text(x,y,text,ha='center',va='center',fontsize=11,color=ink)

    def arrow(points,label=None,label_at=None,color=ink):
        xs,ys=zip(*points)
        if len(points)>2:ax.plot(xs[:-1],ys[:-1],color=color,linewidth=1.4)
        ax.annotate('',xy=points[-1],xytext=points[-2],
            arrowprops={'arrowstyle':'-|>','color':color,'lw':1.4,'mutation_scale':13})
        if label:ax.text(*label_at,label,ha='center',va='center',fontsize=10,color=color,
            bbox={'facecolor':'white','edgecolor':'none','pad':2})

    ax.text(6,14.6,'P5 WiFi Occupancy Lab V1',ha='center',fontsize=21,weight='bold',color=ink)
    ax.text(6,14.18,'Un bus: BUS_001  ·  Dos sondas: SENSOR_01 y SENSOR_02',ha='center',fontsize=12,color=muted)
    x=4.35
    box(x,13.35,5.7,.85,'Abrir la interfaz\nSin conexión ni captura automática',fill='#deeff0')
    box(x,12.05,5.7,.95,'Preparar el experimento\nCondiciones, duración, teléfonos y aforo inicial')
    box(x,10.7,5.7,.95,'Seleccionar y conectar una o dos sondas\nComprobar autopruebas con radio apagada')
    box(x,9.35,5.7,.95,'Confirmar entorno autorizado\nPulsar «Iniciar manualmente»',fill='#deeff0')
    box(x,8.05,5.7,.85,'Recibir registros seriales por sonda\nVentanas de 10 s · canal 6 · 115200 baudios')
    diamond(x,6.8,4.5,1.15,'¿Datos íntegros\ny continuos?')
    box(x,4.95,5.7,1.75,'Visualizar y guardar cada ventana\nProbe Requests y direcciones únicas\nRSSI medio/mín./máx. · canal efectivo\nMemoria libre · eventos descartados\nCSV + JSONL + tiempos y metadatos',size=11)
    diamond(x,3.3,4.5,1.1,'¿Continuar\nla medición?')
    box(x,1.7,5.7,.95,'Detener las sondas y cerrar los puertos\nConservar registros · consultar historial\nComparar estadísticas y exportar CSV / PNG',fill='#deeff0',size=10.5)
    for upper,lower in [(12.925,12.525),(11.575,11.175),(10.225,9.825),(8.875,8.475),(7.625,7.375)]:
        arrow([(x,upper),(x,lower)])
    arrow([(x,6.225),(x,5.825)],'Sí',(x+.28,6.02))
    arrow([(x,4.075),(x,3.85)])
    arrow([(x,2.75),(x,2.175)],'No / fin',(x+.5,2.48))
    arrow([(2.1,3.3),(.55,3.3),(.55,8.05),(1.5,8.05)],'Sí',(.82,3.65))

    box(9.5,6.8,3.7,1.05,'Incidencia crítica\nAbortar y registrar el motivo\nConservar los datos válidos',fill='#fdebea',edge='#ad4040',size=10.5)
    arrow([(6.6,6.8),(7.65,6.8)],'No',(7.12,7.03),color='#ad4040')
    arrow([(11.35,6.8),(11.65,6.8),(11.65,1.7),(7.2,1.7)],color='#ad4040')
    box(9.5,4.65,3.7,2.55,'OPCIONAL · Por sonda\nParámetros B y pd válidos\nN = max(0, (D − B)/pd)\nNO CALIBRADO\nAforo manual y error absoluto\nSin sumar ni fusionar sondas',fill='#fff2ce',size=10.5)
    arrow([(7.2,4.95),(7.65,4.95)],color=teal)
    ax.text(6,.65,'Pausar: STOP confirmado · Reanudar: nuevo segmento manual\nNo rellenar pérdidas con ceros · No guardar MAC, SSID ni contenido de tramas',
        ha='center',va='center',fontsize=10,color=muted,linespacing=1.5)
    for extension in ('png','svg'):
        fig.savefig(output/f'flujo_interfaz_p5.{extension}',dpi=300,facecolor='white')
    plt.close(fig)


if __name__=='__main__':
    main()
