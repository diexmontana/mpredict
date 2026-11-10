# -*- coding: utf-8 -*-
"""
Configuración de mpredict y comprobación de los modelos al arrancar.

    from mpredict import configuracion
    cfg = configuracion.cargar()          # ¡antes de importar maint_predict o sentence_transformers!

cargar():
  1. lee config/mpredict.toml (las variables MPREDICT_DATOS y HF_HOME tienen prioridad);
  2. fija HF_HOME y el modo SIN INTERNET de Hugging Face (los modelos ya se
     descargaron con scripts/descargar_modelos.py o al construir la imagen);
  3. añade maint-predict al camino de Python: modelo.joblib necesita importar
     el módulo con su nombre original, «maint_predict».

comprobar_ficha(carpeta): compara las versiones anotadas en ficha.json con las
instaladas y devuelve una lista de avisos (vacía si todo coincide).
"""
import json
import os
import platform
import sys
import tomllib
from importlib import metadata

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVO = os.path.join(RAIZ, "config", "mpredict.toml")

# nombre en ficha.json -> nombre del paquete instalado
PAQUETES = {"scikit-learn": "scikit-learn", "sentence-transformers": "sentence-transformers",
            "torch": "torch", "pandas": "pandas", "numpy": "numpy", "joblib": "joblib"}
GRAVES = {"scikit-learn"}      # una versión distinta puede cambiar cómo se lee modelo.joblib


def _ruta(valor):
    return valor if os.path.isabs(valor) else os.path.normpath(os.path.join(RAIZ, valor))


def cargar(archivo=ARCHIVO):
    with open(archivo, "rb") as f:
        c = tomllib.load(f)
    cfg = {
        "modelo_tipo": _ruta(c["modelos"]["tipo"]),
        "modelo_tamano": _ruta(c["modelos"]["tamano"]),
        "datos": _ruta(os.environ.get("MPREDICT_DATOS") or c["rutas"]["datos"]),
        "hf_home": _ruta(os.environ.get("HF_HOME") or c["rutas"]["hf_home"]),
    }
    os.environ["HF_HOME"] = cfg["hf_home"]
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    if RAIZ not in sys.path:
        sys.path.insert(0, RAIZ)
    return cfg


def _base(v):
    """«2.15.0+cpu» -> «2.15.0» (el sufijo indica la variante de compilación, no la versión)."""
    return str(v).split("+", 1)[0]


def comprobar_ficha(carpeta):
    """Avisos si las versiones de ficha.json no coinciden con las instaladas."""
    ruta = os.path.join(carpeta, "ficha.json")
    if not os.path.exists(os.path.join(carpeta, "modelo.joblib")) or not os.path.exists(ruta):
        return [{"grave": True, "texto": f"Falta modelo.joblib o ficha.json en {carpeta}"}]
    with open(ruta, encoding="utf-8") as f:
        ficha = json.load(f)
    versiones = ficha.get("versiones", {})
    avisos = []
    if versiones.get("python") and versiones["python"] != platform.python_version():
        avisos.append({"grave": False, "texto": f"Python: la ficha dice {versiones['python']}, "
                                                f"instalado {platform.python_version()}"})
    for clave, paquete in PAQUETES.items():
        if clave not in versiones:
            continue
        try:
            instalada = metadata.version(paquete)
        except metadata.PackageNotFoundError:
            instalada = "no instalado"
        if _base(instalada) != _base(versiones[clave]):
            avisos.append({"grave": clave in GRAVES,
                           "texto": f"{clave}: la ficha dice {versiones[clave]}, instalado {instalada}"})
    if "maint_predict" in versiones:
        import maint_predict
        if maint_predict.VERSION_MODULO != versiones["maint_predict"]:
            avisos.append({"grave": True, "texto": f"maint_predict: la ficha dice {versiones['maint_predict']}, "
                                                   f"el módulo es {maint_predict.VERSION_MODULO}"})
    return avisos
