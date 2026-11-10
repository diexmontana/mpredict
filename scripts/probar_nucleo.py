# -*- coding: utf-8 -*-
"""
Prueba del núcleo por consola (fin de la Parte 2).

    python scripts/probar_nucleo.py

1. «Registra» EvaP como lo hará la pantalla Proyectos: clona su commit ACTUAL de
   GitHub en datos/repos/evap (si ya existe, lo reutiliza), detecta las carpetas,
   calcula los cortes y construye el índice de M92 (solo .py de las carpetas, sin
   pruebas ni migraciones) en datos/indices/evap.
2. Analiza 3 issues en inglés de eval-repos/EvaP-docs/datos/evap_casos.csv
   (elegidos con random.Random(42) entre los que tienen tipo) y 2 tickets escritos
   en español, y mide el tiempo de cada etapa.

OJO: el código actual de EvaP YA contiene los arreglos de esos issues; que M92
encuentre los archivos correctos no prueba que el modelo acierte.
"""
import json
import os
import random
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAIS = os.path.dirname(RAIZ)
sys.path.insert(0, RAIZ)
from mpredict import configuracion   # noqa: E402

cfg = configuracion.cargar()
import pandas as pd                  # noqa: E402

from mpredict import cortes, localizacion, repos   # noqa: E402
from mpredict.analizador import Analizador          # noqa: E402

URL = "https://github.com/e-valuation/EvaP"
REPO = os.path.join(cfg["datos"], "repos", "evap")
INDICE = os.path.join(cfg["datos"], "indices", "evap")

ESPANOL = [
    ("La exportación de resultados a Excel falla si una pregunta no tiene respuestas",
     "Al exportar los resultados de un semestre desde la vista de staff, el archivo no se genera "
     "y aparece un error 500. En el registro se ve un `ZeroDivisionError` en la función que calcula "
     "el promedio. Pasa solo cuando alguna pregunta de la evaluación no recibió respuestas."),
    ("Permitir que los docentes descarguen la lista de participantes",
     "Los docentes responsables quieren descargar en CSV la lista de estudiantes que participan en "
     "su evaluación, para comprobar que está completa antes de que empiece el periodo de votación."),
]

# ------------------------------------------------------------ 1. registro
print("1. Registro de EvaP")
t0 = time.perf_counter()
if os.path.isdir(os.path.join(REPO, ".git")):
    print(f"   ya clonado en {REPO}: se reutiliza")
else:
    print(f"   clonando {URL} (historial completo)...")
    repos.clonar(URL, REPO)
commit = repos.commit_actual(REPO)
print(f"   commit: {commit[:8]}  ({time.perf_counter() - t0:.0f} s)")
propuestas = repos.detectar_carpetas(REPO)
carpetas = list(propuestas)
print(f"   carpetas detectadas: {', '.join(c + '/' for c in carpetas)}")
t1 = time.perf_counter()
c = cortes.calcular_cortes(REPO, "HEAD", carpetas)
print(f"   cortes: pequeño ≤ {c['pequeno_hasta']}, mediano {c['pequeno_hasta'] + 1}–{c['mediano_hasta']}, "
      f"grande > {c['mediano_hasta']}  ({c['commits_usados']} commits, estado {c['estado']}, "
      f"{time.perf_counter() - t1:.0f} s)")
t1 = time.perf_counter()
fc = localizacion.fragmentos_de_carpetas(REPO, carpetas)
meta = localizacion.construir_indice(fc, INDICE, {"commit": commit, "carpetas": carpetas})
with open(os.path.join(INDICE, "cortes.json"), "w", encoding="utf-8") as f:
    json.dump(c, f, ensure_ascii=False, indent=2)
print(f"   índice M92: {meta['archivos']} archivos .py, {meta['fragmentos']} fragmentos "
      f"({time.perf_counter() - t1:.0f} s)")
proyecto = {"nombre": "EvaP", "cortes": c, "indice": INDICE}

# ------------------------------------------------------------ 2. análisis
print("\n2. Cargando el analizador (traductor, modelos de tipo y tamaño, modelo de M92)...")
a = Analizador(cfg)
print(f"   cargado en {a.segundos_carga:.0f} s")

casos = pd.read_csv(os.path.join(TAIS, "eval-repos", "EvaP-docs", "datos", "evap_casos.csv"),
                    encoding="utf-8-sig", dtype=str, keep_default_na=False)
con_tipo = casos[casos["tipo"] != "sin_tipo"].reset_index(drop=True)
elegidos = con_tipo.iloc[sorted(random.Random(42).sample(range(len(con_tipo)), 3))]
tickets = [(f"#{r['numero_issue']} (inglés)", r["titulo"], r["descripcion"], r) for _, r in elegidos.iterrows()]
tickets += [(f"español {i}", t, d, None) for i, (t, d) in enumerate(ESPANOL, 1)]

tiempos = []
for nombre, titulo, descripcion, real in tickets:
    r = a.analizar(titulo, descripcion, proyecto)
    tiempos.append(r["tiempos"] | {"total": r["segundos"]})
    tr, tp, tm, dn = r["traduccion"], r["tipo"], r["tamano"], r["donde"]
    print("\n" + "=" * 78 + f"\n{nombre}: {titulo}")
    if tr["traducido"]:
        print(f"   traducción: {tr['titulo']}\n               {tr['descripcion'][:300]}")
    else:
        print("   sin traducir (ya está en inglés)")
    print("   tipo:   " + " · ".join(f"{p['clase']} {p['probabilidad']:.0%}" for p in tp["probabilidades"]))
    print(f"   tamaño: {tm['clase']} ({tm['rango'] or 'sin rango'}) · "
          + " · ".join(f"{p['clase']} {p['probabilidad']:.0%}" for p in tm["probabilidades"]))
    print("   dónde:  " + ("ERROR " + dn["error"] if dn["error"] else ""))
    for x in dn["archivos"]:
        print(f"           {x['puntaje']:.4f}  {x['archivo']}")
    if real is not None:
        print(f"   real (dataset, solo como referencia): tipo {real['tipo']}, {real['lineas']} líneas; "
              f"archivos {real['archivos'][:150]}")
    print("   tiempos: " + ", ".join(f"{k} {v:.2f} s" for k, v in r["tiempos"].items())
          + f" | total {r['segundos']:.2f} s")

T = pd.DataFrame(tiempos)
print("\n" + "=" * 78 + "\nTiempo por ticket (s):")
print(T.agg(["mean", "max"]).round(2).to_string())
print("\nRecordatorio: el código actual de EvaP ya contiene los arreglos de los issues en inglés.")
