# -*- coding: utf-8 -*-
"""
Cortes de tamaño de un proyecto (pequeño / mediano / grande).

Misma lógica que maint-predict-docs/preparar_datos.py para EvaP y Baby Buddy:
  - unidad: cada commit de la rama principal comparado con su PRIMER PADRE
    (git log --first-parent --diff-merges=first-parent), desde el 01-01-2020;
  - se excluyen los commits de bots (dependabot, renovate);
  - líneas = añadidas + borradas en los archivos de las carpetas de código,
    salvo las pruebas; solo cuentan los commits que cambian alguna línea;
  - cortes = percentiles 30 y 80 de esas líneas, redondeados.

Funciones COPIADAS de preparar_datos.py (se indica la función de origen en cada una).
Únicos cambios: el repositorio, el commit y las carpetas son parámetros (antes
estaban fijos en REPOS), y los errores se lanzan como ErrorGit en lugar de sys.exit,
para que la aplicación pueda mostrarlos.

Añadido (regla aprobada en la Parte 1): según cuántos commits con código haya
  - 100 o más: cortes normales;
  - 30 a 99:   cortes «con aviso» (rango poco fiable);
  - menos de 30: no se calculan cortes.
"""
import re
import subprocess

import numpy as np

DESDE = "2020-01-01"                     # preparar_datos.py, DESDE
BOTS = ("dependabot", "renovate")        # preparar_datos.py, BOTS
MINIMO_NORMAL = 100
MINIMO_CON_AVISO = 30


class ErrorGit(RuntimeError):
    pass


def git(repo, *args):
    """preparar_datos.git: git en modo solo lectura (--no-optional-locks)."""
    try:
        r = subprocess.run(["git", "--no-optional-locks", "-C", repo, *args], capture_output=True)
    except FileNotFoundError:
        raise ErrorGit("No encuentro el programa git.")
    if r.returncode != 0:
        raise ErrorGit(f"git falló: git {' '.join(args)}\n{r.stderr.decode('utf-8', 'replace')}")
    return r.stdout.decode("utf-8", "replace")


def interpretar(salida):
    """preparar_datos.interpretar (sin cambios). numstat con -z; binarios = 0 líneas."""
    trozos, filas, k = salida.split("\0"), [], 0
    while k < len(trozos):
        t = trozos[k].lstrip("\n")
        if not t:
            k += 1
            continue
        an, bo, ruta = t.split("\t", 2)
        if ruta == "":                       # renombrado: se usa la ruta nueva
            ruta, k = trozos[k + 2], k + 3
        else:
            k += 1
        binario = an == "-"
        filas.append((ruta, 0 if binario else int(an), 0 if binario else int(bo)))
    return filas


def es_prueba(ruta):
    """preparar_datos.es_prueba (sin cambios)."""
    nombre = ruta.rsplit("/", 1)[-1]
    return "/tests/" in ruta or re.fullmatch(r"test_.*\.py", nombre) is not None or nombre == "tests.py"


def cuenta(carpetas, ruta):
    """preparar_datos.cuenta, rama de EvaP y Baby Buddy, con las carpetas como parámetro."""
    return ruta.split("/", 1)[0] in carpetas and "/" in ruta and not es_prueba(ruta)


def historial(repo, ref, carpetas, desde=DESDE):
    """preparar_datos.historial, modo EvaP / Baby Buddy (primer padre)."""
    git(repo, "cat-file", "-e", ref + "^{commit}")                  # el commit debe existir
    salida = git(repo, "log", ref, "--first-parent", "--diff-merges=first-parent", f"--since={desde}",
                 "-z", "--format=%x01%H%x1f%P%x1f%cs%x1f%an", "--numstat")
    commits = []
    for bloque in salida.split("\x01")[1:]:
        cabecera, _, resto = bloque.partition("\0")
        sha, padres, fecha, autor = cabecera.split("\x1f")
        archivos = interpretar(resto)
        lineas = sum(a + b for ruta, a, b in archivos if cuenta(carpetas, ruta))
        commits.append({"sha": sha, "fecha": fecha, "autor": autor, "lineas": lineas,
                        "bot": any(x in autor.lower() for x in BOTS)})
    return commits


def calcular_cortes(repo, ref, carpetas, desde=DESDE):
    """preparar_datos.calcular_cortes para un solo proyecto, más la regla de mínimo de commits."""
    carpetas = tuple(carpetas)
    cs = historial(repo, ref, carpetas, desde)
    validos = [c for c in cs if c["fecha"] >= desde and not c["bot"] and c["lineas"] > 0]
    n = len(validos)
    corte = {
        "commits_usados": n, "commits_leidos": len(cs),
        "commits_bot_excluidos": sum(c["bot"] for c in cs),
        "commits_sin_codigo_excluidos": sum((not c["bot"]) and c["lineas"] == 0 for c in cs),
        "commit_fijado": git(repo, "rev-parse", ref).strip(), "desde": desde,
        "carpetas": list(carpetas), "percentiles": [30, 80],
        "unidad": "commit de la rama principal contra su primer padre",
        "regla": "todo archivo bajo las carpetas de código, salvo pruebas",
    }
    if n < MINIMO_CON_AVISO:
        corte.update(estado="sin_cortes",
                     aviso=f"Solo hay {n} commits con código desde {desde}: no se calculan cortes de tamaño.")
        return corte
    L = np.array([c["lineas"] for c in validos])
    p30, p80 = np.percentile(L, [30, 80])
    corte.update(
        pequeno_hasta=int(round(p30)), mediano_hasta=int(round(p80)),
        percentil_30_exacto=float(p30), percentil_80_exacto=float(p80),
        mediana_lineas=float(np.median(L)),
        primer_commit=min(c["fecha"] for c in validos), ultimo_commit=max(c["fecha"] for c in validos))
    if n < MINIMO_NORMAL:
        corte.update(estado="con_aviso",
                     aviso=f"Cortes calculados con {n} commits (menos de {MINIMO_NORMAL}): rango poco fiable.")
    else:
        corte.update(estado="normal", aviso="")
    return corte


def categoria(lineas, corte):
    """preparar_datos.categoria (sin cambios)."""
    if lineas == 0:
        return "sin_codigo"
    if lineas <= corte["pequeno_hasta"]:
        return "pequeño"
    return "mediano" if lineas <= corte["mediano_hasta"] else "grande"


def rango_texto(clase, corte):
    """Rango de líneas de una clase de tamaño, para mostrarlo en la nota."""
    if corte.get("estado") == "sin_cortes":
        return None
    p, m = corte["pequeno_hasta"], corte["mediano_hasta"]
    return {"pequeño": f"≤ {p} líneas", "mediano": f"{p + 1}–{m} líneas", "grande": f"> {m} líneas"}[clase]
