# -*- coding: utf-8 -*-
"""
Comprobación 2: los cortes de EvaP en el commit 8c2ac6b6 deben coincidir con
maint-predict-docs/datos/cortes_tamano.json (pequeño ≤ 9, mediano 10–202).

    python scripts/verificar_cortes.py

Solo LEE eval-repos/EvaP (git con --no-optional-locks) y maint-predict-docs.
Las carpetas de código salen de repos.detectar_carpetas, la misma función
que usará la pantalla Proyectos (se espera: evap).
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAIS = os.path.dirname(RAIZ)
sys.path.insert(0, RAIZ)

from mpredict import cortes, repos   # noqa: E402

EVAP = os.path.join(TAIS, "eval-repos", "EvaP")
REFERENCIA = os.path.join(TAIS, "maint-predict-docs", "datos", "cortes_tamano.json")
COMMIT = "8c2ac6b6e853a68e3b1cbb75b3ce1f5968af0cd9"
CAMPOS = ["pequeno_hasta", "mediano_hasta", "percentil_30_exacto", "percentil_80_exacto", "mediana_lineas",
          "commits_usados", "commits_leidos", "commits_bot_excluidos", "commits_sin_codigo_excluidos",
          "primer_commit", "ultimo_commit"]

propuestas = repos.detectar_carpetas(EVAP)
print("Carpetas detectadas en EvaP:")
for c, motivos in propuestas.items():
    print(f"  {c}/  <- {motivos[0]}" + (f"  (+{len(motivos) - 1} motivos más)" if len(motivos) > 1 else ""))
carpetas = list(propuestas)
if carpetas != ["evap"]:
    print(f"AVISO: se esperaba solo evap/ y salió {carpetas}. Se calcula igual con evap/.")
    carpetas = ["evap"]

print(f"\nCalculando cortes de EvaP en {COMMIT[:8]} (solo lectura)...")
nuevo = cortes.calcular_cortes(EVAP, COMMIT, carpetas)
ref = json.load(open(REFERENCIA, encoding="utf-8"))["proyectos"]["evap"]

print(f"\n{'campo':<30}{'cortes_tamano.json':>22}{'mpredict':>14}")
iguales = 0
for c in CAMPOS:
    ok = ref[c] == nuevo[c]
    iguales += ok
    print(f"{c:<30}{str(ref[c]):>22}{str(nuevo[c]):>14}  {'igual' if ok else 'DISTINTO'}")
print(f"\nResultado: {iguales} de {len(CAMPOS)} campos iguales. "
      f"Cortes mpredict: pequeño ≤ {nuevo['pequeno_hasta']}, mediano {nuevo['pequeno_hasta'] + 1}–"
      f"{nuevo['mediano_hasta']}, grande > {nuevo['mediano_hasta']} (estado: {nuevo['estado']}).")
sys.exit(0 if iguales == len(CAMPOS) else 1)
