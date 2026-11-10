#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
M9.2 - Localizador de archivos Django (reconstrucción operativa).
Método: BM25 + embeddings multilingual MiniLM + Weighted RRF (80/20).
No usa etiquetas/commits de solución para construir el ranking.
"""
import argparse, ast, json, re, sys
from pathlib import Path
import pandas as pd
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MAX_CHARS = 1500
INITIAL_CHUNKS = 6
GUIDED_CHUNKS = 12
RRF_K = 60
BM25_WEIGHT = 0.80
SEMANTIC_WEIGHT = 0.20

def tokenize(text):
    return re.findall(r"[A-Za-z_][A-Za-z_0-9]*|[^\W\d_]+|\d+", str(text).lower(), flags=re.UNICODE)

def split_python(path, root):
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    rel = path.relative_to(root).as_posix()
    lines = source.splitlines()
    chunks = []
    try:
        tree = ast.parse(source)
        nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        nodes.sort(key=lambda n: (getattr(n, "lineno", 0), getattr(n, "end_lineno", 0)))
        for n in nodes:
            start = max(1, getattr(n, "lineno", 1))
            end = min(len(lines), getattr(n, "end_lineno", start))
            body = "\n".join(lines[start-1:end])
            if len(body) > MAX_CHARS:
                body = body[:MAX_CHARS]
            if body.strip():
                chunks.append({"file": rel, "text": f"FILE: {rel}\nSYMBOL: {getattr(n,'name','')}\n{body}"})
    except SyntaxError:
        pass
    # Complemento: ventanas de líneas para módulos sin nodos AST o archivos con poco contenido estructurado.
    if not chunks:
        step = 35
        for i in range(0, len(lines), step):
            body = "\n".join(lines[i:i+step])[:MAX_CHARS]
            if body.strip():
                chunks.append({"file": rel, "text": f"FILE: {rel}\n{body}"})
    return chunks

def load_repo(repo):
    files = sorted(p for p in repo.rglob("*.py") if ".git" not in p.parts and "__pycache__" not in p.parts)
    all_chunks, file_chunks = [], {}
    for p in files:
        rel = p.relative_to(repo).as_posix()
        chunks = split_python(p, repo)
        if chunks:
            file_chunks[rel] = chunks
            all_chunks.extend(chunks)
    return file_chunks, len(files)

def query_text(row):
    title = str(row.get("summary", row.get("title", "")) or "")
    body = str(row.get("texto_modelo", "") or "")
    if not body.strip() or body.lower() == "nan":
        body = str(row.get("description", row.get("descripcion_sin_enlaces", "")) or "")
    return (title + "\n" + body).strip()

def retrieve_one(row, file_chunks, model, topn=20):
    query = query_text(row)
    if not query:
        raise ValueError(f"Ticket {row.get('id','?')} no tiene summary/description.")
    # Mantener los primeros seis chunks de cada archivo y añadir hasta doce chunks
    # guiados por BM25 entre las funciones/clases del propio archivo.
    selected = []
    for fname, chunks in file_chunks.items():
        initial = chunks[:INITIAL_CHUNKS]
        toks = [tokenize(c["text"]) for c in chunks]
        bm = BM25Okapi(toks) if toks else None
        guided_idx = []
        if bm and chunks:
            scores = bm.get_scores(tokenize(query))
            guided_idx = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:GUIDED_CHUNKS]
        seen = set()
        for i in list(range(min(INITIAL_CHUNKS, len(chunks)))) + guided_idx:
            if i not in seen:
                selected.append(chunks[i])
                seen.add(i)
    if not selected:
        return []
    # BM25: ranking de archivos a partir de los chunks seleccionados.
    tokenized = [tokenize(c["text"]) for c in selected]
    bm = BM25Okapi(tokenized)
    chunk_scores = bm.get_scores(tokenize(query))
    bm_file = {}
    for c, score in zip(selected, chunk_scores):
        bm_file[c["file"]] = max(bm_file.get(c["file"], float("-inf")), float(score))
    bm_rank = sorted(bm_file, key=bm_file.get, reverse=True)
    # Semántica: similitud coseno ticket-fragmento y máximo por archivo.
    texts = [c["text"] for c in selected]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False, batch_size=64)
    qemb = model.encode([query], normalize_embeddings=True, show_progress_bar=False)
    sims = cosine_similarity(qemb, embeddings)[0]
    sem_file = {}
    for c, score in zip(selected, sims):
        sem_file[c["file"]] = max(sem_file.get(c["file"], float("-inf")), float(score))
    sem_rank = sorted(sem_file, key=sem_file.get, reverse=True)
    # Weighted Reciprocal Rank Fusion. RRF se aplica a rankings de archivos.
    fused = {}
    for rank, f in enumerate(bm_rank, 1):
        fused[f] = fused.get(f, 0.0) + BM25_WEIGHT / (RRF_K + rank)
    for rank, f in enumerate(sem_rank, 1):
        fused[f] = fused.get(f, 0.0) + SEMANTIC_WEIGHT / (RRF_K + rank)
    ordered = sorted(fused, key=fused.get, reverse=True)
    return [{"rank": i+1, "archivo": f, "score_rrf": fused[f],
             "score_bm25": bm_file.get(f), "score_semantico": sem_file.get(f)}
            for i, f in enumerate(ordered[:topn])]

def main():
    ap = argparse.ArgumentParser(description="M9.2 reconstruido: localización Top-K de archivos Python.")
    ap.add_argument("--repo", required=True, help="Ruta al clon/snapshot de Django.")
    ap.add_argument("--input", required=True, help="CSV de tickets con id, summary y description/texto_modelo.")
    ap.add_argument("--out", default="resultados_m92", help="Carpeta de salida.")
    ap.add_argument("--top", type=int, default=20, help="Cantidad de archivos por ticket.")
    ap.add_argument("--ticket", type=int, default=None, help="Procesar solo un ID de ticket.")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    csv_path = Path(args.input).resolve()
    out = Path(args.out).resolve()
    if not repo.exists(): raise SystemExit(f"No existe el repositorio: {repo}")
    if not csv_path.exists(): raise SystemExit(f"No existe el CSV: {csv_path}")
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(csv_path).fillna("")
    if args.ticket is not None:
        df = df[df["id"].astype(str) == str(args.ticket)]
    if df.empty: raise SystemExit("No hay tickets para procesar.")
    print("Indexando archivos Python del snapshot...")
    file_chunks, nfiles = load_repo(repo)
    nchunks = sum(map(len, file_chunks.values()))
    print(f"Archivos Python detectados: {nfiles}; archivos con fragmentos: {len(file_chunks)}; chunks AST: {nchunks}")
    print(f"Cargando modelo de embeddings: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)
    rows = []
    for _, row in df.iterrows():
        preds = retrieve_one(row, file_chunks, model, topn=args.top)
        tid = row.get("id", "")
        for p in preds:
            rows.append({"ticket": tid, **p})
        if preds:
            print(f"Ticket {tid}: Top-5 = " + ", ".join(x["archivo"] for x in preds[:5]))
    result = pd.DataFrame(rows)
    result.to_csv(out / "predicciones_m92.csv", index=False, encoding="utf-8-sig")
    meta = {"metodo":"M9.2 reconstruido", "embedding_model":MODEL_NAME,
            "bm25_weight":BM25_WEIGHT, "semantic_weight":SEMANTIC_WEIGHT,
            "rrf_k":RRF_K, "initial_chunks_per_file":INITIAL_CHUNKS,
            "guided_chunks_per_file":GUIDED_CHUNKS, "max_chars_per_chunk":MAX_CHARS,
            "repo":str(repo), "python_files_detected":nfiles, "files_indexed":len(file_chunks),
            "chunks_indexed":nchunks, "tickets_processed":int(df.shape[0])}
    (out / "configuracion_m92.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResultados guardados en: {out}")

if __name__ == "__main__":
    main()
