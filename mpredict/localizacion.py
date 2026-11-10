# -*- coding: utf-8 -*-
"""
DÓNDE: adaptador de M92 (m92_original.py, copia sin cambios del módulo del compañero).

Qué NO cambia (se importa del original): el troceo de los .py (split_python), la
tokenización, el modelo multilingüe, los 6 fragmentos iniciales + 12 guiados por
BM25 por archivo, el BM25 global sobre lo seleccionado, la similitud coseno, el
máximo por archivo y la fusión RRF ponderada 80 % BM25 / 20 % semántica (k = 60).

Qué cambia:
  1. Es una función: buscar(titulo, texto_modelo) sobre el índice de un proyecto.
  2. Los embeddings de TODOS los fragmentos se calculan UNA vez al registrar el
     proyecto (construir_indice) y se guardan; en cada ticket se usan los guardados
     en lugar de recalcular los de los fragmentos seleccionados.
  3. El BM25 de cada archivo no depende del ticket: se construye una vez al cargar.
  4. Entrada: en mpredict se indexan solo los .py de las carpetas de código
     confirmadas, sin pruebas ni migraciones (el original indexaba todo el repositorio).
     Para comprobar la equivalencia, construir_indice también acepta el mismo
     conjunto de archivos que el original (m92_original.load_repo).

La consulta es la de query_text del original: título + "\\n" + texto_modelo.
"""
import json
import os
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.metrics.pairwise import cosine_similarity

from . import m92_original as m92
from .cortes import es_prueba

VERSION_ADAPTADOR = "1.0"
TOP = 5


def parametros():
    return {"metodo": "M9.2 reconstruido (adaptado por mpredict)", "embedding_model": m92.MODEL_NAME,
            "bm25_weight": m92.BM25_WEIGHT, "semantic_weight": m92.SEMANTIC_WEIGHT, "rrf_k": m92.RRF_K,
            "initial_chunks_per_file": m92.INITIAL_CHUNKS, "guided_chunks_per_file": m92.GUIDED_CHUNKS,
            "max_chars_per_chunk": m92.MAX_CHARS, "adaptador": VERSION_ADAPTADOR}


_MODELO = None


def modelo():
    """El modelo multilingüe de M92, cargado una sola vez (desde la caché local)."""
    global _MODELO
    if _MODELO is None:
        from sentence_transformers import SentenceTransformer
        _MODELO = SentenceTransformer(m92.MODEL_NAME)
    return _MODELO


# =====================================================================
# Índice
# =====================================================================
def fragmentos_de_carpetas(repo, carpetas):
    """Fragmentos de los .py de las carpetas de código, sin pruebas ni migraciones.
    Mismo recorrido y troceo que m92_original.load_repo, filtrando las rutas."""
    repo = Path(repo).resolve()
    archivos = sorted(p for p in repo.rglob("*.py") if ".git" not in p.parts and "__pycache__" not in p.parts)
    file_chunks = {}
    for p in archivos:
        rel = p.relative_to(repo).as_posix()
        if rel.split("/", 1)[0] not in carpetas or es_prueba(rel) or "/migrations/" in "/" + rel:
            continue
        chunks = m92.split_python(p, repo)
        if chunks:
            file_chunks[rel] = chunks
    return file_chunks


def construir_indice(file_chunks, destino, info=None, progreso=False):
    """Calcula y guarda los embeddings de TODOS los fragmentos (una vez por proyecto)."""
    textos = [c["text"] for chunks in file_chunks.values() for c in chunks]
    E = modelo().encode(textos, normalize_embeddings=True, show_progress_bar=progreso, batch_size=64)
    os.makedirs(destino, exist_ok=True)
    np.save(os.path.join(destino, "embeddings.npy"), np.asarray(E))
    with open(os.path.join(destino, "fragmentos.json"), "w", encoding="utf-8") as f:
        json.dump([[archivo, [c["text"] for c in chunks]] for archivo, chunks in file_chunks.items()],
                  f, ensure_ascii=False)
    meta = {"parametros": parametros(), "archivos": len(file_chunks), "fragmentos": len(textos), **(info or {})}
    with open(os.path.join(destino, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


class Indice:
    """Índice cargado en memoria: fragmentos, embeddings guardados y BM25 por archivo."""

    def __init__(self, carpeta):
        with open(os.path.join(carpeta, "fragmentos.json"), encoding="utf-8") as f:
            datos = json.load(f)
        with open(os.path.join(carpeta, "meta.json"), encoding="utf-8") as f:
            self.meta = json.load(f)
        self.E = np.load(os.path.join(carpeta, "embeddings.npy"))
        self.file_chunks, self.inicio, self.tokens, self.bm_archivo = {}, {}, [], {}
        k = 0
        for archivo, textos in datos:                 # mismo orden que en el original
            self.file_chunks[archivo] = [{"file": archivo, "text": t} for t in textos]
            self.inicio[archivo] = k
            toks = [m92.tokenize(t) for t in textos]
            self.tokens += toks
            self.bm_archivo[archivo] = BM25Okapi(toks)
            k += len(textos)
        if k != len(self.E):
            raise ValueError(f"El índice está dañado: {k} fragmentos y {len(self.E)} embeddings.")

    # -----------------------------------------------------------------
    def buscar(self, titulo, texto_modelo, topn=TOP):
        """Misma lógica que m92_original.retrieve_one, con los embeddings guardados."""
        query = (str(titulo or "") + "\n" + str(texto_modelo or "")).strip()   # query_text
        if not query:
            raise ValueError("El ticket no tiene título ni descripción.")
        qtok = m92.tokenize(query)
        # 6 iniciales + 12 guiados por BM25 dentro de cada archivo
        selected = []
        for fname, chunks in self.file_chunks.items():
            base = self.inicio[fname]
            scores = self.bm_archivo[fname].get_scores(qtok)
            guided_idx = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:m92.GUIDED_CHUNKS]
            seen = set()
            for i in list(range(min(m92.INITIAL_CHUNKS, len(chunks)))) + guided_idx:
                if i not in seen:
                    selected.append(base + i)
                    seen.add(i)
        if not selected:
            return []
        archivo_de = [self.file_chunks_archivo(g) for g in selected]
        # BM25 global sobre los fragmentos seleccionados
        chunk_scores = BM25Okapi([self.tokens[g] for g in selected]).get_scores(qtok)
        bm_file = {}
        for f, score in zip(archivo_de, chunk_scores):
            bm_file[f] = max(bm_file.get(f, float("-inf")), float(score))
        bm_rank = sorted(bm_file, key=bm_file.get, reverse=True)
        # Semántica con los embeddings GUARDADOS
        qemb = modelo().encode([query], normalize_embeddings=True, show_progress_bar=False)
        sims = cosine_similarity(qemb, self.E[selected])[0]
        sem_file = {}
        for f, score in zip(archivo_de, sims):
            sem_file[f] = max(sem_file.get(f, float("-inf")), float(score))
        sem_rank = sorted(sem_file, key=sem_file.get, reverse=True)
        # RRF ponderado
        fused = {}
        for rank, f in enumerate(bm_rank, 1):
            fused[f] = fused.get(f, 0.0) + m92.BM25_WEIGHT / (m92.RRF_K + rank)
        for rank, f in enumerate(sem_rank, 1):
            fused[f] = fused.get(f, 0.0) + m92.SEMANTIC_WEIGHT / (m92.RRF_K + rank)
        ordered = sorted(fused, key=fused.get, reverse=True)
        return [{"rank": i + 1, "archivo": f, "score_rrf": fused[f],
                 "score_bm25": bm_file.get(f), "score_semantico": sem_file.get(f)}
                for i, f in enumerate(ordered[:topn])]

    def file_chunks_archivo(self, g):
        if not hasattr(self, "_archivo_de"):
            self._archivo_de = [a for a, ch in self.file_chunks.items() for _ in ch]
        return self._archivo_de[g]
