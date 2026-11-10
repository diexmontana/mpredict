# -*- coding: utf-8 -*-
"""
Comprobación 3 (a): el M92 adaptado da el mismo top 5 que el original.

    python scripts/verificar_m92.py

- Archivos: los MISMOS que indexa el original, m92_original.load_repo sobre
  eval-repos/EvaP (todos los .py del repositorio, commit 8c2ac6b6). Solo lectura.
- Tickets: 20 issues de EvaP (maint-predict-docs/datos/dataset_unificado.csv,
  uso = prueba_evap), elegidos con random.Random(42).
- Consulta: la de query_text del original, con summary = título y
  texto_modelo = maint_predict.texto_modelo(título, descripción).
- Original: m92_original.retrieve_one (recalcula embeddings en cada ticket: lento).
  Adaptado: localizacion.Indice.buscar con los embeddings precalculados.
El índice de esta prueba se guarda en datos/verificacion/m92_evap_completo.
"""
import os
import random
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAIS = os.path.dirname(RAIZ)
sys.path.insert(0, RAIZ)
from mpredict import configuracion   # noqa: E402

cfg = configuracion.cargar()
from pathlib import Path             # noqa: E402

import maint_predict as mp           # noqa: E402
import pandas as pd                  # noqa: E402

from mpredict import localizacion, m92_original as m92   # noqa: E402

EVAP = Path(TAIS, "eval-repos", "EvaP").resolve()
DESTINO = os.path.join(cfg["datos"], "verificacion", "m92_evap_completo")

df = pd.read_csv(os.path.join(TAIS, "maint-predict-docs", "datos", "dataset_unificado.csv"),
                 encoding="utf-8-sig", dtype=str, keep_default_na=False)
evap = df[df["uso"] == "prueba_evap"].reset_index(drop=True)
muestra = evap.iloc[sorted(random.Random(42).sample(range(len(evap)), 20))]

print("1. Troceando el repositorio con m92_original.load_repo (mismos archivos que el original)...")
file_chunks, nfiles = m92.load_repo(EVAP)
print(f"   {nfiles} archivos .py; {len(file_chunks)} con fragmentos; "
      f"{sum(map(len, file_chunks.values()))} fragmentos")

print("2. Precalculando los embeddings de TODOS los fragmentos (lo que mpredict hace al registrar)...")
t0 = time.perf_counter()
localizacion.construir_indice(file_chunks, DESTINO, {"repo": str(EVAP), "uso": "verificación (a)"}, progreso=True)
indice = localizacion.Indice(DESTINO)
print(f"   índice listo en {time.perf_counter() - t0:.0f} s")
modelo = localizacion.modelo()

print("3. Comparando el top 5 en 20 tickets (el original tarda bastante en cada uno)...\n")
iguales_orden = iguales_conjunto = 0
t_orig = t_adap = 0.0
for n, (_, f) in enumerate(muestra.iterrows(), 1):
    row = {"id": f["id"], "summary": f["titulo"], "texto_modelo": mp.texto_modelo(f["titulo"], f["descripcion"])}
    t1 = time.perf_counter()
    orig = [x["archivo"] for x in m92.retrieve_one(row, file_chunks, modelo, topn=5)]
    t2 = time.perf_counter()
    adap = [x["archivo"] for x in indice.buscar(row["summary"], row["texto_modelo"])]
    t3 = time.perf_counter()
    t_orig += t2 - t1
    t_adap += t3 - t2
    mismo_orden, mismo_conj = orig == adap, set(orig) == set(adap)
    iguales_orden += mismo_orden
    iguales_conjunto += mismo_conj
    estado = "IGUAL" if mismo_orden else ("mismos archivos, otro orden" if mismo_conj else "DISTINTO")
    print(f"[{n:>2}/20] #{f['id']:<5} {estado:<28} original {t2 - t1:5.1f} s | adaptado {t3 - t2:4.2f} s")
    if not mismo_orden:
        print(f"         original: {orig}\n         adaptado: {adap}")

print(f"\nResultado: top 5 idéntico (mismo orden) en {iguales_orden} de 20; mismos 5 archivos en "
      f"{iguales_conjunto} de 20.")
print(f"Tiempo medio por ticket: original {t_orig / 20:.1f} s; adaptado {t_adap / 20:.2f} s.")
