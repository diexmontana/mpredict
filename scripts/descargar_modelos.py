# -*- coding: utf-8 -*-
"""
Descarga los tres modelos de Hugging Face que usa mpredict y comprueba que
cargan SIN internet.

    python scripts/descargar_modelos.py

Dónde los guarda: en la carpeta indicada por la variable HF_HOME. Si no está
definida, en  <maint-predict>/datos/hf  (dentro del proyecto y fuera de Git,
porque datos/ está en .gitignore). Así no se crea nada fuera de TAIS.
La imagen de Docker (Parte 4) usa este mismo script al construirse.

Modelos:
  - sentence-transformers/all-MiniLM-L6-v2                      tipo y tamaño (maint_predict.py)
  - sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 dónde (M92)
  - Helsinki-NLP/opus-mt-es-en                                  traducción español -> inglés

Al terminar escribe <HF_HOME>/modelos_descargados.json con la versión exacta
(commit de Hugging Face) de cada modelo.
"""
import datetime
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# HF_HOME debe fijarse ANTES de importar huggingface_hub, que lo lee al importarse
os.environ.setdefault("HF_HOME", os.path.join(RAIZ, "datos", "hf"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
HF_HOME = os.environ["HF_HOME"]

from huggingface_hub import list_repo_files, snapshot_download   # noqa: E402

MODELOS = {
    "sentence-transformers/all-MiniLM-L6-v2": "tipo y tamaño (maint_predict.py)",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": "dónde (M92)",
    "Helsinki-NLP/opus-mt-es-en": "traducción español -> inglés",
}
# Formatos de pesos que mpredict no usa (solo PyTorch): no se descargan para ahorrar espacio
NO_DESCARGAR = ["*.onnx", "onnx/*", "openvino/*", "*.h5", "*.msgpack", "*.ot", "*.tflite"]


def descargar():
    print(f"Carpeta de modelos (HF_HOME): {HF_HOME}\n")
    versiones = {}
    for nombre, uso in MODELOS.items():
        print(f"Descargando {nombre}  [{uso}] ...")
        ignorar = list(NO_DESCARGAR)
        if "model.safetensors" in list_repo_files(nombre):
            ignorar.append("*.bin")              # mismos pesos en otro formato: basta con uno
        ruta = snapshot_download(nombre, ignore_patterns=ignorar)
        commit = os.path.basename(ruta)          # .../snapshots/<commit>
        versiones[nombre] = {"uso": uso, "commit": commit}
        print(f"   listo (commit {commit})")
    return versiones


def comprobar_sin_internet():
    """Carga cada modelo solo desde la caché local (local_files_only=True)."""
    print("\nComprobando que cada modelo carga sin internet...")
    from sentence_transformers import SentenceTransformer
    for nombre in list(MODELOS)[:2]:
        m = SentenceTransformer(nombre, local_files_only=True)
        v = m.encode(["The admin crashes when saving a model."], normalize_embeddings=True)
        print(f"   {nombre}: vector de {v.shape[1]} números")
    from transformers import MarianMTModel, MarianTokenizer
    nombre = "Helsinki-NLP/opus-mt-es-en"
    tok = MarianTokenizer.from_pretrained(nombre, local_files_only=True)
    mod = MarianMTModel.from_pretrained(nombre, local_files_only=True)
    frase = "El panel de administración falla al guardar el formulario."
    salida = mod.generate(**tok([frase], return_tensors="pt"))
    print(f"   {nombre}: «{frase}» -> «{tok.decode(salida[0], skip_special_tokens=True)}»")


if __name__ == "__main__":
    try:
        versiones = descargar()
    except Exception as e:
        sys.exit(f"\nERROR al descargar: {type(e).__name__}: {e}")
    comprobar_sin_internet()
    os.makedirs(HF_HOME, exist_ok=True)
    with open(os.path.join(HF_HOME, "modelos_descargados.json"), "w", encoding="utf-8") as f:
        json.dump({"descargado": datetime.datetime.now().isoformat(timespec="seconds"),
                   "modelos": versiones}, f, ensure_ascii=False, indent=2)
    print(f"\nTodo listo. Versiones anotadas en {os.path.join(HF_HOME, 'modelos_descargados.json')}")
