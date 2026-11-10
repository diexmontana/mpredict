# -*- coding: utf-8 -*-
"""
Repositorios de los proyectos: clonar, actualizar y detectar las carpetas de código.

- El clon es COMPLETO (sin --depth ni --shallow-since): en un clon recortado el
  commit del borde no tiene padre y git contaría todo el árbol como añadido,
  lo que inflaría los cortes de tamaño.
- La detección de carpetas NUNCA ejecuta código del repositorio: lee los
  archivos como texto y analiza INSTALLED_APPS con el módulo ast de Python.
"""
import ast
import os
import re
import subprocess

from .cortes import ErrorGit, git

RE_URL_GITHUB = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?(\.git)?/?$")
IGNORAR = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", ".tox", "site-packages"}
NO_SON_CODIGO = {"tests", "test", "docs", "doc"}     # carpetas de primer nivel que nunca se proponen


def validar_url(url):
    url = (url or "").strip()
    if not RE_URL_GITHUB.match(url):
        raise ValueError("La URL debe tener la forma https://github.com/<dueño>/<repositorio>")
    return url.rstrip("/")


def clonar(url, destino):
    """git clone completo. Devuelve la rama principal."""
    url = validar_url(url)
    if os.path.exists(destino) and os.listdir(destino):
        raise ErrorGit(f"La carpeta {destino} ya existe y no está vacía.")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    r = subprocess.run(["git", "clone", "--quiet", url, destino], capture_output=True)
    if r.returncode != 0:
        raise ErrorGit(f"No se pudo clonar {url}:\n{r.stderr.decode('utf-8', 'replace')}")
    return rama_principal(destino)


def rama_principal(destino):
    """Rama a la que apunta origin/HEAD (p. ej. «main»)."""
    return git(destino, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip().split("/", 1)[1]


def actualizar(destino):
    """Trae los commits nuevos y deja el clon en la última versión de la rama principal."""
    git(destino, "fetch", "--quiet", "--prune", "origin")
    rama = rama_principal(destino)
    git(destino, "checkout", "--quiet", "-B", rama, f"origin/{rama}")
    return rama


def commit_actual(destino):
    return git(destino, "rev-parse", "HEAD").strip()


# ------------------------------------------------------------------ detección
def _recorrer(raiz):
    for actual, dirs, archivos in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in IGNORAR and not d.startswith(".")]
        yield actual, archivos


def _apps_en_installed_apps(arbol):
    """Cadenas de INSTALLED_APPS = [...], INSTALLED_APPS += [...] o sumas de listas."""
    def cadenas(nodo):
        if isinstance(nodo, (ast.List, ast.Tuple)):
            return [e.value for e in nodo.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Add):
            return cadenas(nodo.left) + cadenas(nodo.right)
        return []

    encontradas = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.Assign):
            destinos, valor = n.targets, n.value
        elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
            destinos, valor = [n.target], n.value
        else:
            continue
        if any(isinstance(d, ast.Name) and d.id == "INSTALLED_APPS" for d in destinos) and valor is not None:
            encontradas += cadenas(valor)
    return encontradas


def detectar_carpetas(raiz):
    """Carpetas de primer nivel propuestas como código, con el motivo de cada una.

    Devuelve {carpeta: [motivos]}. Dos fuentes:
      1. contiene apps.py o models.py (a cualquier profundidad);
      2. una app de INSTALLED_APPS cuyo primer nombre es esa carpeta.
    """
    primer_nivel = sorted(d for d in os.listdir(raiz)
                          if os.path.isdir(os.path.join(raiz, d)) and d not in IGNORAR
                          and not d.startswith(".") and d.lower() not in NO_SON_CODIGO)
    propuestas = {}

    for d in primer_nivel:
        for actual, archivos in _recorrer(os.path.join(raiz, d)):
            hallados = sorted({"apps.py", "models.py"} & set(archivos))
            if hallados:
                rel = os.path.relpath(os.path.join(actual, hallados[0]), raiz).replace(os.sep, "/")
                propuestas.setdefault(d, []).append(f"contiene {rel}")
                break

    for actual, archivos in _recorrer(raiz):
        for a in archivos:
            if not a.endswith(".py"):
                continue
            ruta = os.path.join(actual, a)
            try:
                texto = open(ruta, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            if "INSTALLED_APPS" not in texto:
                continue
            try:
                apps = _apps_en_installed_apps(ast.parse(texto))
            except SyntaxError:
                continue
            rel = os.path.relpath(ruta, raiz).replace(os.sep, "/")
            for app in apps:
                d = app.split(".", 1)[0]
                if d in primer_nivel:
                    motivo = f"«{app}» en INSTALLED_APPS ({rel})"
                    if motivo not in propuestas.setdefault(d, []):
                        propuestas[d].append(motivo)
    return dict(sorted(propuestas.items()))


def carpetas_de_primer_nivel(raiz):
    """Todas las carpetas de primer nivel, para que la pantalla permita corregir la propuesta."""
    return sorted(d for d in os.listdir(raiz)
                  if os.path.isdir(os.path.join(raiz, d)) and d not in IGNORAR and not d.startswith("."))
