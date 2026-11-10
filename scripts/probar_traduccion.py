# -*- coding: utf-8 -*-
"""
Prueba de la traducción con 6 casos. Para cada uno muestra el texto antes y
después y comprueba que cada trozo de código protegido aparece IDÉNTICO en la
traducción.

    python scripts/probar_traduccion.py
"""
import os
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from mpredict import configuracion   # noqa: E402

configuracion.cargar()
from mpredict.traduccion import Traductor, proteger   # noqa: E402

CASOS = [
    ("Español con nombres técnicos",
     "El método QuerySet.filter() devuelve resultados duplicados",
     "Al llamar a `Evaluation.objects.filter(course__semester=s)` desde la vista staff_semester_view "
     "aparecen evaluaciones repetidas. Creo que el problema está en evap/staff/views.py."),
    ("Español con traceback",
     "Error al guardar el formulario de evaluación",
     "Cuando el administrador guarda el formulario aparece este error:\n\n"
     "Traceback (most recent call last):\n  File \"evap/staff/views.py\", line 120, in save\n"
     "    form.save()\nKeyError: 'contributor'\n\nDebería guardarse sin problemas."),
    ("Español con bloque de código",
     "Los puntos de recompensa no se descuentan",
     "Al canjear puntos el saldo no cambia. Ejemplo:\n\n```python\nevent.redeem(user, points=5)\n"
     "assert user.reward_points == 0\n```\n\nEl saldo sigue igual después de recargar la página."),
    ("Inglés (no debe traducirse)",
     "Results page crashes when there are no answers",
     "Opening the results of an evaluation without answers raises a `ZeroDivisionError`."),
    ("Mixto: título en inglés, descripción en español",
     "Export fails for empty semesters",
     "La exportación a Excel falla si el semestre no tiene evaluaciones publicadas."),
    ("Vacío", "", ""),
]

t0 = time.perf_counter()
tr = Traductor()
print(f"Traductor cargado en {time.perf_counter() - t0:.1f} s\n")
total_ok = 0
for nombre, titulo, descripcion in CASOS:
    t1 = time.perf_counter()
    r = tr.traducir_ticket(titulo, descripcion)
    seg = time.perf_counter() - t1
    protegidos = proteger(titulo)[1] + proteger(descripcion)[1]
    salida = r["titulo"] + "\n" + r["descripcion"]
    intactos = sum(p in salida for p in protegidos)
    ok = intactos == len(protegidos)
    total_ok += ok
    print("=" * 78)
    print(f"{nombre}  |  idioma título={r['idioma']['titulo'] or '-'}, descripción={r['idioma']['descripcion'] or '-'}"
          f"  |  traducido={'sí' if r['traducido'] else 'no'}  |  método={', '.join(r['metodos']) or '-'}  |  {seg:.1f} s")
    print(f"--- antes ---\n{titulo}\n{descripcion}")
    print(f"--- después ---\n{r['titulo']}\n{r['descripcion']}")
    print(f"--- código protegido intacto: {intactos} de {len(protegidos)} {'OK' if ok else 'FALLA'}")
print("=" * 78)
print(f"Resultado: {total_ok} de {len(CASOS)} casos con todo el código intacto.")
