# -*- coding: utf-8 -*-
"""
maint_predict — MÓDULO COMPARTIDO de TAIS (modelos para cualquier proyecto Django).

Es el único archivo que necesita una aplicación para usar los modelos:

    import maint_predict as mp
    mp.predecir("Título del ticket", "Descripción...", "tipo")
    -> {"clase": "Bug", "probabilidades": {"Bug": 0.71, ...}, "modelo": "...", "version": "..."}

Contiene, en un solo lugar, todo lo que convierte un ticket en las entradas del
modelo, para que entrenamiento y uso sean idénticos:

  1. limpiar_texto(t): formato wiki de Trac (Django) **y** Markdown de GitHub
     (EvaP, Baby Buddy) -> texto plano. Parte de limpiar_texto de
     app/datos/limpiar_dataset.py (paso L6), cuyas reglas se conservan sin cambios.
  2. texto_modelo(titulo, descripcion): «<título sin punto final>. <descripción limpia>»,
     igual que l6_texto_para_modelo de app/datos/limpiar_dataset.py.
  3. rasgos(descripcion): tiene_traceback, tiene_codigo, n_palabras_descripcion.
     RE_TRACEBACK y RE_CODIGO vienen de app/datos/construir_dataset.py; a RE_CODIGO
     se le añaden los bloques de Markdown.
  4. calcular_embeddings(textos): all-MiniLM-L6-v2, igual que calcular_embeddings
     de app/modelos/entrenar_nivel2.py. Solo usa la caché local de Hugging Face:
     NUNCA descarga nada (si no encuentra el modelo, lo dice y se detiene).
  5. PreparadorTicket: pieza de scikit-learn que hace 2–4. Va DENTRO de cada
     modelo.joblib, así el modelo guardado recibe solo título y descripción.
  6. predecir / predecir_lote: cargan modelos/<tipo|tamano>/modelo.joblib y ficha.json.

Las funciones se COPIAN (no se importan) desde app/ para no crear archivos
__pycache__ dentro de app/, que no se debe modificar.

Comprobaciones por consola (desde maint-predict-docs, con el entorno activado):
    python maint_predict.py --probar-limpieza     ejemplos de Trac y Markdown, antes y después
    python maint_predict.py --probar-lenguaje     comprueba que el modelo de lenguaje está en la caché
    python maint_predict.py tipo "título" "descripción"     predice (cuando ya hay modelos)
"""
import json
import os
import re
import sys

# El modelo de lenguaje se usa SOLO desde la caché local: estas dos variables se
# fijan antes de importar sentence-transformers / huggingface_hub, de modo que
# ninguna parte del programa pueda descargar nada por su cuenta.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import numpy as np                                     # noqa: E402
import pandas as pd                                    # noqa: E402
from sklearn.base import BaseEstimator, TransformerMixin  # noqa: E402

VERSION_MODULO = "1.0"
AQUI = os.path.dirname(os.path.abspath(__file__))
CARPETA_MODELOS = os.path.join(AQUI, "modelos")

# Nombre completo del mismo modelo que usó entrenar_nivel2.py ("all-MiniLM-L6-v2"):
# con el nombre completo se encuentra en la caché sin consultar internet.
MODELO_LENGUAJE = "sentence-transformers/all-MiniLM-L6-v2"
N_EMB = 384
EMB = [f"e{i}" for i in range(N_EMB)]

TEXTO = "texto_modelo"
BINARIAS = ["tiene_traceback", "tiene_codigo"]
NUMERICAS = ["n_palabras_descripcion"]
ENTRADAS = [TEXTO] + EMB + BINARIAS + NUMERICAS


# =====================================================================
# 1. Limpieza del texto (Trac + Markdown)
# =====================================================================
RE_URL = re.compile(r"https?://\S+")

# --- reglas nuevas para Markdown de GitHub (no aparecen en el wiki de Trac)
RE_COMENTARIO_HTML = re.compile(r"<!--.*?-->", re.S)                 # restos de plantillas de issue
RE_IMAGEN_MD = re.compile(r"!\[[^\]\n]*\]\([^)\n]*\)")              # ![alt](url)
RE_IMAGEN_HTML = re.compile(r"<img\b[^>]*>", re.I)                    # <img src=...>
# [texto](destino): solo si el destino es claramente un enlace (http, mailto, / , # , ./),
# para no tocar código Python como lista[0](x)
RE_ENLACE_MD = re.compile(r"\[([^\]\n]+)\]\(\s*(?:https?://|mailto:|/|#|\./)[^)\s]*(?:\s+\"[^\"]*\")?\s*\)")
RE_AUTOENLACE = re.compile(r"<(https?://[^>\s]+)>")                  # <https://...>
# PR y commits de CUALQUIER repositorio de GitHub (antes: solo django/django)
RE_PR = re.compile(r"https?://github\.com/[\w.-]+/[\w.-]+/pull/\S+", re.I)
RE_COMMIT = re.compile(r"https?://github\.com/[\w.-]+/[\w.-]+/commit/\S+", re.I)
# línea que abre o cierra un bloque de código: ```python, ```, ~~~
RE_VALLA_MD = re.compile(r"(?m)^[ \t]*(?:`{3,}|~{3,})[ \t]*[\w+#.-]*[ \t]*$")
# **negrita** de Markdown: solo pares en la misma línea y no pegados a letras,
# para no tocar **kwargs ni x**2 del código Python
RE_NEGRITA_MD = re.compile(r"(?<![\w*])\*\*(?=\S)([^*\n]+?)(?<=\S)\*\*(?![\w*])")
# títulos ## a ######. El «# » simple no se quita: en el código Python es un comentario
RE_TITULO_MD = re.compile(r"(?m)^[ \t]{0,3}#{2,6}[ \t]+")


def limpiar_texto(t):
    """Convierte el formato wiki de Trac y el Markdown de GitHub en texto plano.

    Las reglas de Trac son las de app/datos/limpiar_dataset.py (paso L6), en el
    mismo orden; las de Markdown se intercalan donde corresponde (imágenes antes
    que enlaces, enlaces antes que URLs sueltas). El código se conserva siempre:
    solo se quitan las marcas que lo rodean."""
    t = t or ""
    t = t.replace("​", "")                                    # espacio invisible (Trac)
    t = RE_COMENTARIO_HTML.sub(" ", t)                             # MD: <!-- ... -->
    t = re.sub(r"\[\[Image\([^)]*\)\]\]", " [imagen] ", t)         # Trac: imágenes
    t = RE_IMAGEN_MD.sub(" [imagen] ", t)                          # MD: ![alt](url)
    t = RE_IMAGEN_HTML.sub(" [imagen] ", t)                        # MD: <img ...>
    t = RE_ENLACE_MD.sub(r"\1", t)                                 # MD: [texto](url) -> texto
    t = RE_AUTOENLACE.sub(r"\1", t)                                # MD: <url> -> url
    t = re.sub(r"\[(https?://\S+)\s+([^\]]+)\]", r"\2", t)         # Trac: [url texto] -> texto
    t = re.sub(r"\[(https?://\S+)\]", r"\1", t)                    # Trac: [url] -> url
    t = RE_PR.sub(" [enlace-PR] ", t)                              # enlaces a PR (cualquier repo)
    t = RE_COMMIT.sub(" [enlace-commit] ", t)                      # enlaces a commits
    t = RE_URL.sub(" [enlace] ", t)                                # otros enlaces
    t = re.sub(r"\{\{\{\s*(#!\w+)?", " ", t)                       # Trac: inicio de bloque
    t = t.replace("}}}", " ")                                      # Trac: fin de bloque
    t = RE_VALLA_MD.sub(" ", t)                                    # MD: ```python / ``` / ~~~
    t = re.sub(r"'''|''", "", t)                                   # Trac: negrita / cursiva
    t = RE_NEGRITA_MD.sub(r"\1", t)                                # MD: **negrita**
    t = RE_TITULO_MD.sub("", t)                                    # MD: ## Título
    t = re.sub(r"\s+", " ", t)                                     # espacios repetidos
    return t.strip()


def texto_modelo(titulo, descripcion):
    """«<título sin punto final>. <descripción limpia>», como el paso L6."""
    titulo = (titulo or "").strip().rstrip(".")
    return (titulo + ". " + limpiar_texto(descripcion)).strip()


# =====================================================================
# 2. Rasgos del texto
# =====================================================================
RE_TRACEBACK = re.compile(r"Traceback \(most recent call last\)", re.I)   # de construir_dataset.py
RE_CODIGO_TRAC = re.compile(r"\{\{\{")                                      # de construir_dataset.py
# Markdown: solo BLOQUES (una línea que empieza con ``` o ~~~). El código en
# línea `x` no cuenta, igual que en Django no contaba.
RE_CODIGO_MD = re.compile(r"(?m)^[ \t]*(?:`{3,}|~{3,})")


def rasgos(descripcion):
    """Se calculan sobre la descripción ORIGINAL (sin limpiar), como en construir_dataset.py."""
    d = descripcion or ""
    return {"tiene_traceback": int(bool(RE_TRACEBACK.search(d))),
            "tiene_codigo": int(bool(RE_CODIGO_TRAC.search(d) or RE_CODIGO_MD.search(d))),
            "n_palabras_descripcion": len(d.split())}


def preparar(titulos, descripciones):
    """Tabla con texto_modelo y los tres rasgos (sin embeddings)."""
    titulos = ["" if t is None else str(t) for t in titulos]
    descripciones = ["" if d is None else str(d) for d in descripciones]
    filas = []
    for t, d in zip(titulos, descripciones):
        f = {TEXTO: texto_modelo(t, d)}
        f.update(rasgos(d))
        filas.append(f)
    return pd.DataFrame(filas, columns=[TEXTO] + BINARIAS + NUMERICAS)


# =====================================================================
# 3. Vectores de significado (embeddings)
# =====================================================================
_CODIFICADOR = None


def codificador():
    """Carga all-MiniLM-L6-v2 desde la caché local (una sola vez por ejecución)."""
    global _CODIFICADOR
    if _CODIFICADOR is None:
        from sentence_transformers import SentenceTransformer
        try:
            _CODIFICADOR = SentenceTransformer(MODELO_LENGUAJE, local_files_only=True)
        except Exception as e:
            raise RuntimeError(
                f"No encuentro el modelo de lenguaje {MODELO_LENGUAJE} en la caché local de "
                "Hugging Face. No se descargó nada. Avísale a quien te ayuda antes de descargarlo.\n"
                f"Detalle: {type(e).__name__}: {e}") from e
    return _CODIFICADOR


def calcular_embeddings(textos, mostrar_progreso=False):
    """384 números por texto; normalize_embeddings=True, como en entrenar_nivel2.py."""
    return codificador().encode(list(textos), batch_size=32, show_progress_bar=mostrar_progreso,
                                normalize_embeddings=True)


def con_embeddings(tabla, E):
    """Añade las columnas e0..e383 a una tabla preparada."""
    tabla = tabla.reset_index(drop=True)
    return pd.concat([tabla, pd.DataFrame(np.asarray(E), columns=EMB)], axis=1)


class PreparadorTicket(BaseEstimator, TransformerMixin):
    """Primera pieza de cada modelo.joblib.

    Entrada: tabla con columnas «titulo» y «descripcion».
    Salida: tabla con texto_modelo, e0..e383, tiene_traceback, tiene_codigo y
    n_palabras_descripcion, que es lo que espera la regresión logística.
    No aprende nada (no tiene parámetros), por eso fit no hace nada."""

    def fit(self, X, y=None):
        return self

    def __sklearn_is_fitted__(self):
        return True

    def transform(self, X):
        tabla = preparar(X["titulo"], X["descripcion"])
        return con_embeddings(tabla, calcular_embeddings(tabla[TEXTO]))


# =====================================================================
# 4. Uso de los modelos guardados
# =====================================================================
_CARGADOS = {}


def carpeta_de(cual):
    """'tipo' o 'tamano' -> modelos/<cual>; también acepta una ruta a otra carpeta."""
    return cual if os.path.isdir(cual) else os.path.join(CARPETA_MODELOS, cual)


def cargar(cual):
    """Devuelve (modelo, ficha) de una carpeta de modelo. Se cargan una sola vez."""
    carpeta = carpeta_de(cual)
    if carpeta not in _CARGADOS:
        import joblib
        ruta_modelo = os.path.join(carpeta, "modelo.joblib")
        if not os.path.exists(ruta_modelo):
            raise FileNotFoundError(f"No existe {ruta_modelo}. Ejecuta antes entrenar.py.")
        with open(os.path.join(carpeta, "ficha.json"), encoding="utf-8") as f:
            ficha = json.load(f)
        _CARGADOS[carpeta] = (joblib.load(ruta_modelo), ficha)
    return _CARGADOS[carpeta]


def predecir_lote(titulos, descripciones, cual):
    """Predice muchos tickets a la vez. Devuelve una tabla con la columna «clase»
    y una columna «p_<clase>» por cada clase."""
    modelo, _ = cargar(cual)
    X = pd.DataFrame({"titulo": list(titulos), "descripcion": list(descripciones)})
    P = modelo.predict_proba(X)
    clases = [str(c) for c in modelo.classes_]
    salida = pd.DataFrame(P, columns=[f"p_{c}" for c in clases])
    salida.insert(0, "clase", [clases[i] for i in P.argmax(axis=1)])
    return salida


def predecir(titulo, descripcion, cual="tipo"):
    """Lo que llamaría una aplicación: un ticket -> clase y probabilidades."""
    modelo, ficha = cargar(cual)
    fila = predecir_lote([titulo], [descripcion], cual).iloc[0]
    clases = [str(c) for c in modelo.classes_]
    return {"clase": fila["clase"],
            "probabilidades": {c: round(float(fila[f"p_{c}"]), 4) for c in clases},
            "modelo": ficha.get("nombre"), "version": ficha.get("version")}


# =====================================================================
# 5. Comprobaciones por consola
# =====================================================================
EJEMPLOS = [
    ("Trac (Django)",
     "Crash in admin\n\nSee ​[https://github.com/django/django/pull/12926 PR] and "
     "https://sqlite.org/x.html\n{{{#!python\ndef f(**kwargs):\n    return x**2  # nada\n}}}\n"
     "'''importante''' [[Image(captura.png)]]"),
    ("Markdown (GitHub)",
     "<!-- plantilla: describe el error -->\n## Steps to reproduce\n"
     "Open [the page](https://example.org/a) and see ![shot](https://x.org/s.png).\n"
     "Fixed in https://github.com/e-valuation/EvaP/pull/2310 and <https://evap.org>.\n"
     "```python\nTraceback (most recent call last):\n  File \"views.py\"\n```\n"
     "**Expected**: no error with `lista[0](x)` nor **kwargs."),
]


def _probar_limpieza():
    for nombre, d in EJEMPLOS:
        print(f"\n=== {nombre} ===\n--- antes ---\n{d}\n--- texto_modelo ---")
        print(texto_modelo("Título de ejemplo.", d))
        print("--- rasgos ---", rasgos(d))


def _probar_lenguaje():
    E = calcular_embeddings(["The admin crashes when saving a model."])
    print(f"Modelo de lenguaje cargado desde la caché local: {MODELO_LENGUAJE}")
    print(f"Vector de {E.shape[1]} números (se esperaban {N_EMB}); longitud = {np.linalg.norm(E[0]):.3f} (se espera 1.000)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--probar-limpieza"]:
        _probar_limpieza()
    elif args == ["--probar-lenguaje"]:
        _probar_lenguaje()
    elif len(args) == 3 and args[0] in ("tipo", "tamano"):
        print(json.dumps(predecir(args[1], args[2], args[0]), ensure_ascii=False, indent=2))
    else:
        print(__doc__)
