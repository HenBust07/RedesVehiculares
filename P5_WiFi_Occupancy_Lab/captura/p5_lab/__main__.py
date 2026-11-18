"""Entrada local; sin conexion automatica ni instalacion de dependencias."""
import argparse
import importlib
import json
import os
from pathlib import Path
import sys


def main():
    root=Path(__file__).resolve().parents[2]
    os.environ.setdefault('PYTHONDONTWRITEBYTECODE','1')
    os.environ.setdefault('MPLCONFIGDIR',str(root/'results/lab_v1/mplconfig'))
    parser=argparse.ArgumentParser(description='P5 WiFi Occupancy Lab V1')
    parser.add_argument('--demo',action='store_true',help='Solo emulacion en memoria, datos sinteticos')
    parser.add_argument('--check',action='store_true',help='Comprobar dependencias sin abrir GUI ni puertos')
    parser.add_argument('--smoke-test',action='store_true',help='Prueba GUI automatizada exclusivamente sintetica')
    args=parser.parse_args()
    versions={}
    try:
        for name in ['tkinter','serial','matplotlib']:
            module=importlib.import_module(name)
            versions[name]=str(getattr(module,'__version__',getattr(module,'TkVersion','presente')))
    except ImportError as exc:
        print('Falta dependencia: '+str(exc)+'. No se instala nada automaticamente.',file=sys.stderr)
        return 2
    if args.check:
        print(json.dumps({'python':sys.version,'executable':sys.executable,'dependencies':versions,'ports_opened':False},indent=2));return 0
    import tkinter as tk
    from .app import LabApp
    window=tk.Tk()
    if args.smoke_test:
        from .smoke import run
        return run(window,root)
    LabApp(window,root,demo=args.demo)
    window.mainloop()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
