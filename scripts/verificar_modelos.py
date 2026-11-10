# -*- coding: utf-8 -*-
"""
Comprobación 1: los modelos copiados en maint-predict/modelos reproducen
maint-predict-docs/predicciones_evap.csv.

    python scripts/verificar_modelos.py

Entrada: los 788 issues de EvaP (uso = prueba_evap) de
maint-predict-docs/datos/dataset_unificado.csv, el mismo título y descripción
que usó evaluar.py. Se predicen con mpredict.clasificacion (como lo hará la
aplicación) y se comparan con el CSV: la clase y las probabilidades, que el
CSV guarda redondeadas a 4 decimales (igual se redondean aquí).
Solo lee maint-predict-docs.
"""
import os
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from mpredict import configuracion   # noqa: E402

cfg = configuracion.cargar()
import pandas as pd                   # noqa: E402
from mpredict.clasificacion import Clasificador   # noqa: E402

DOCS = os.path.join(os.path.dirname(RAIZ), "maint-predict-docs")
leer = lambda r: pd.read_csv(r, encoding="utf-8-sig", dtype=str, keep_default_na=False)   # noqa: E731

print("Cargando los modelos de", cfg["modelo_tipo"], "y", cfg["modelo_tamano"])
c = Clasificador(cfg)
for cual, avisos in c.avisos.items():
    print(f"   {cual}: {c.fichas[cual]['nombre']} v{c.fichas[cual]['version']} -> "
          + ("versiones iguales a la ficha" if not avisos else "; ".join(a["texto"] for a in avisos)))

evap = leer(os.path.join(DOCS, "datos", "dataset_unificado.csv"))
evap = evap[evap["uso"] == "prueba_evap"].reset_index(drop=True)
ref = leer(os.path.join(DOCS, "predicciones_evap.csv"))
assert list(evap["id"]) == list(ref["numero_issue"]), "Los issues no están en el mismo orden"
print(f"\nPrediciendo {len(evap)} issues de EvaP...")
t0 = time.perf_counter()
fallos = 0
for cual in ("tipo", "tamano"):
    p = c.predecir_lote(evap["titulo"], evap["descripcion"], cual)
    clases_iguales = int((p["clase"].values == ref[f"{cual}_predicho"].values).sum())
    cols = [k for k in p.columns if k.startswith("p_")]
    dif = max(float((p[k].round(4) - ref[f"{cual}_{k}"].astype(float)).abs().max()) for k in cols)
    exactas = int(sum((p[k].round(4) == ref[f"{cual}_{k}"].astype(float)).all() for k in cols))
    print(f"   {cual:<7} clase igual en {clases_iguales} de {len(evap)} | "
          f"columnas de probabilidad idénticas: {exactas} de {len(cols)} | diferencia máxima {dif:.4f}")
    fallos += (clases_iguales != len(evap))
print(f"\n({time.perf_counter() - t0:.0f} s)  Resultado: "
      + ("los modelos copiados REPRODUCEN predicciones_evap.csv." if not fallos
         else "hay diferencias en la clase predicha (ver arriba)."))
sys.exit(1 if fallos else 0)
