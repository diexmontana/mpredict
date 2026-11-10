# -*- coding: utf-8 -*-
"""
Analizador: une las piezas del núcleo. Todo se carga UNA vez (al arrancar mpredict).

    a = Analizador(cfg)
    r = a.analizar(titulo, descripcion, proyecto)
    # proyecto = {"nombre": ..., "cortes": {...}, "indice": <carpeta del índice M92>}

Orden:
  1. traducir título y descripción al inglés (si vienen en español);
  2. tipo y tamaño con los modelos de config/mpredict.toml, sobre el texto en inglés;
  3. rango de líneas del tamaño con los cortes del proyecto;
  4. dónde (M92) con la consulta título_en + "\\n" + texto_modelo(título_en, descripción_en).
Cada etapa mide su tiempo. Si M92 falla, el resto del análisis se devuelve igual.
"""
import os
import time

import maint_predict as mp

from . import localizacion
from .clasificacion import Clasificador
from .cortes import rango_texto
from .traduccion import Traductor

AVISO_TAMANO = ("Estimación de baja confianza: en EvaP, el modelo de tamaño acertó con exactitud "
                "equilibrada 0,478 (el azar da 0,333).")
AVISO_DONDE = ("Reconstrucción del método M9.2 (BM25 80 % + embeddings 20 %). Solo analiza archivos "
               "Python (.py) de las carpetas de código, sin pruebas ni migraciones.")


def _ordenar(probabilidades):
    return [{"clase": c, "probabilidad": p} for c, p in sorted(probabilidades.items(), key=lambda x: -x[1])]


class Analizador:
    def __init__(self, cfg):
        t0 = time.perf_counter()
        self.traductor = Traductor()
        self.clasificador = Clasificador(cfg)
        localizacion.modelo().encode(["calentar"], show_progress_bar=False)
        self._indices = {}
        self.segundos_carga = time.perf_counter() - t0

    @property
    def avisos_modelos(self):
        return self.clasificador.avisos

    def indice(self, carpeta):
        """Índice M92 de un proyecto, en memoria; se recarga si se reconstruyó."""
        marca = os.path.getmtime(os.path.join(carpeta, "meta.json"))
        if carpeta not in self._indices or self._indices[carpeta][0] != marca:
            self._indices[carpeta] = (marca, localizacion.Indice(carpeta))
        return self._indices[carpeta][1]

    def analizar(self, titulo, descripcion, proyecto):
        tiempos, t = {}, time.perf_counter()

        tr = self.traductor.traducir_ticket(titulo or "", descripcion or "")
        tiempos["traduccion"] = time.perf_counter() - t

        t = time.perf_counter()
        pred = self.clasificador.predecir(tr["titulo"], tr["descripcion"])
        tiempos["tipo_y_tamano"] = time.perf_counter() - t

        cortes = proyecto.get("cortes") or {"estado": "sin_cortes", "aviso": "El proyecto no tiene cortes."}
        clase_tam = pred["tamano"]["clase"]
        tamano = {"clase": clase_tam, "probabilidades": _ordenar(pred["tamano"]["probabilidades"]),
                  "modelo": pred["tamano"]["modelo"], "version": pred["tamano"]["version"],
                  "rango": rango_texto(clase_tam, cortes), "aviso": AVISO_TAMANO,
                  "aviso_cortes": cortes.get("aviso", ""),
                  "cortes": {k: cortes.get(k) for k in ("pequeno_hasta", "mediano_hasta", "commits_usados",
                                                         "estado", "commit_fijado")}}
        tipo = {"clase": pred["tipo"]["clase"], "probabilidades": _ordenar(pred["tipo"]["probabilidades"]),
                "modelo": pred["tipo"]["modelo"], "version": pred["tipo"]["version"]}

        t = time.perf_counter()
        donde = {"archivos": [], "aviso": AVISO_DONDE, "error": ""}
        try:
            ind = self.indice(proyecto["indice"])
            consulta = mp.texto_modelo(tr["titulo"], tr["descripcion"])
            donde["archivos"] = [{"archivo": r["archivo"], "puntaje": r["score_rrf"],
                                  "bm25": r["score_bm25"], "semantico": r["score_semantico"]}
                                 for r in ind.buscar(tr["titulo"], consulta)]
            donde["indice"] = {k: ind.meta.get(k) for k in ("commit", "carpetas", "archivos", "fragmentos")}
            donde["parametros"] = localizacion.parametros()
        except Exception as e:                                  # el resto del análisis sigue valiendo
            donde["error"] = f"{type(e).__name__}: {e}"
        tiempos["donde"] = time.perf_counter() - t

        return {"proyecto": proyecto.get("nombre"), "traduccion": tr, "tipo": tipo, "tamano": tamano,
                "donde": donde, "tiempos": tiempos, "segundos": sum(tiempos.values())}
