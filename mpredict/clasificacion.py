# -*- coding: utf-8 -*-
"""
Tipo y tamaño: carga los dos modelos UNA vez y predice con maint_predict.

maint_predict.predecir acepta la ruta de una carpeta de modelo, así que la
carpeta sale de config/mpredict.toml sin modificar la copia de maint_predict.py.
"""
import maint_predict as mp

from . import configuracion


class Clasificador:
    def __init__(self, cfg):
        self.rutas = {"tipo": cfg["modelo_tipo"], "tamano": cfg["modelo_tamano"]}
        self.avisos = {}
        self.fichas = {}
        for cual, ruta in self.rutas.items():
            self.avisos[cual] = configuracion.comprobar_ficha(ruta)
            _, ficha = mp.cargar(ruta)                      # se carga aquí, una sola vez
            self.fichas[cual] = {"nombre": ficha.get("nombre"), "version": ficha.get("version"),
                                 "entrenado": ficha.get("entrenado")}
        mp.calcular_embeddings(["calentar el modelo de lenguaje"])   # la primera llamada es más lenta

    def predecir(self, titulo, descripcion):
        """{'tipo': {...}, 'tamano': {...}} con clase, probabilidades, modelo y versión."""
        return {cual: mp.predecir(titulo, descripcion, ruta) for cual, ruta in self.rutas.items()}

    def predecir_lote(self, titulos, descripciones, cual):
        return mp.predecir_lote(titulos, descripciones, self.rutas[cual])
