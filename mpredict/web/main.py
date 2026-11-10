# -*- coding: utf-8 -*-
"""
Aplicación web de mpredict (FastAPI).

    uvicorn mpredict.web.main:app --host 127.0.0.1 --port 8600

Pantalla (la única propia de mpredict):
    /proyectos                     registrar, confirmar carpetas, ver estado, actualizar
Para el complemento de osTicket:
    POST /api/analizar             analiza un ticket y devuelve la nota en HTML
Enlaces de la nota:
    /decision/<código>/aceptar     piden confirmación y guardan la decisión
    /decision/<código>/descartar
Otros:
    GET /api/estado                modelos cargados, avisos de versiones y proyectos
    /docs                          documentación automática de la API
"""
from mpredict import configuracion

CFG = configuracion.cargar()          # antes de importar maint_predict y los modelos

import os                             # noqa: E402
import secrets                        # noqa: E402
import threading                      # noqa: E402
from contextlib import asynccontextmanager   # noqa: E402

from fastapi import FastAPI, Form, HTTPException, Request   # noqa: E402
from fastapi.responses import HTMLResponse, RedirectResponse   # noqa: E402
from fastapi.staticfiles import StaticFiles   # noqa: E402
from fastapi.templating import Jinja2Templates   # noqa: E402
from pydantic import BaseModel, Field   # noqa: E402

from mpredict import VERSION, localizacion   # noqa: E402
from mpredict.analizador import Analizador   # noqa: E402
from mpredict.db import BaseDatos   # noqa: E402
from mpredict.nota import nota_html   # noqa: E402
from mpredict.registro import EN_CURSO, Registro   # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
URL_PUBLICA = os.environ.get("MPREDICT_URL_PUBLICA", "http://127.0.0.1:8600")
ESTADOS = {"descargando": "descargando", "por_confirmar": "por confirmar carpetas", "preparando": "preparando",
           "listo": "listo", "listo_con_aviso": "listo con aviso", "error": "error"}

estado = {}
_bloqueo_analisis = threading.Lock()


@asynccontextmanager
async def ciclo_de_vida(app):
    print("mpredict: cargando traductor y modelos (unos segundos)...")
    estado["db"] = BaseDatos(os.path.join(CFG["datos"], "mpredict.sqlite"))
    estado["registro"] = Registro(estado["db"], CFG)
    estado["analizador"] = Analizador(CFG)
    for cual, avisos in estado["analizador"].avisos_modelos.items():
        for a in avisos:
            print(f"AVISO ({cual}){' GRAVE' if a['grave'] else ''}: {a['texto']}")
    print(f"mpredict listo en {URL_PUBLICA}/proyectos")
    yield


app = FastAPI(title="mpredict", version=VERSION, lifespan=ciclo_de_vida,
              description="Pre-análisis de solicitudes de mantenimiento para proyectos Django: "
                          "tipo, tamaño y dónde.")
app.mount("/estatico", StaticFiles(directory=os.path.join(AQUI, "estatico")), name="estatico")
plantillas = Jinja2Templates(directory=os.path.join(AQUI, "plantillas"))
plantillas.env.globals["ESTADOS"] = ESTADOS


def _avisos():
    return [dict(a, modelo=c) for c, lista in estado["analizador"].avisos_modelos.items() for a in lista]


# ================================================================ pantalla Proyectos
@app.get("/", include_in_schema=False)
def inicio():
    return RedirectResponse("/proyectos")


@app.get("/proyectos", response_class=HTMLResponse, include_in_schema=False)
def ver_proyectos(request: Request, error: str = "", nombre: str = "", url: str = ""):
    ps = estado["db"].proyectos()
    return plantillas.TemplateResponse(request, "proyectos.html", {
        "proyectos": ps, "error": error, "nombre": nombre, "url": url, "avisos": _avisos(),
        "refrescar": any(p["estado"] in EN_CURSO for p in ps)})


@app.post("/proyectos", include_in_schema=False)
def registrar_proyecto(request: Request, nombre: str = Form(""), url: str = Form("")):
    try:
        estado["registro"].registrar(nombre, url)
    except ValueError as e:
        return ver_proyectos(request, error=str(e), nombre=nombre, url=url)
    return RedirectResponse("/proyectos", status_code=303)


@app.get("/proyectos/{pid}/carpetas", response_class=HTMLResponse, include_in_schema=False)
def ver_carpetas(request: Request, pid: int, error: str = ""):
    p = estado["db"].proyecto(pid)
    if not p or not p.get("carpetas_disponibles"):
        raise HTTPException(404, "Proyecto sin carpetas detectadas todavía.")
    marcadas = p.get("carpetas") or list((p.get("carpetas_propuestas") or {}).keys())
    return plantillas.TemplateResponse(request, "carpetas.html", {"p": p, "marcadas": marcadas, "error": error})


@app.post("/proyectos/{pid}/carpetas", include_in_schema=False)
async def confirmar_carpetas(request: Request, pid: int):
    formulario = await request.form()
    try:
        estado["registro"].confirmar(pid, formulario.getlist("carpeta"))
    except ValueError as e:
        return ver_carpetas(request, pid, error=str(e))
    return RedirectResponse("/proyectos", status_code=303)


@app.post("/proyectos/{pid}/actualizar", include_in_schema=False)
def actualizar_proyecto(request: Request, pid: int):
    try:
        estado["registro"].actualizar(pid)
    except ValueError as e:
        return ver_proyectos(request, error=str(e))
    return RedirectResponse("/proyectos", status_code=303)


# ================================================================ API para el complemento
class Ticket(BaseModel):
    ticket_numero: str = Field("", description="Número del ticket en osTicket")
    titulo: str = Field(..., description="Título (asunto) del ticket")
    descripcion: str = Field("", description="Descripción (primer mensaje), en texto")
    tema_id: int | None = Field(None, description="Id del tema de ayuda de osTicket (= proyecto)")
    tema_nombre: str = Field("", description="Nombre del tema de ayuda, p. ej. «Proyecto EvaP»")


@app.post("/api/analizar", tags=["API"], summary="Analiza un ticket y devuelve la nota en español")
def api_analizar(t: Ticket):
    db = estado["db"]
    p = db.proyecto_por_tema(t.tema_id, t.tema_nombre)
    if p is None:
        raise HTTPException(404, f"El tema «{t.tema_nombre or t.tema_id}» no corresponde a ningún proyecto "
                                 "registrado en mpredict.")
    if p["estado"] not in ("listo", "listo_con_aviso"):
        raise HTTPException(409, f"El proyecto {p['nombre']} todavía no está listo "
                                 f"(estado: {ESTADOS.get(p['estado'], p['estado'])}).")
    with _bloqueo_analisis:
        r = estado["analizador"].analizar(t.titulo, t.descripcion,
                                          {"nombre": p["nombre"], "cortes": p["cortes"], "indice": p["indice"]})
    codigo = secrets.token_urlsafe(16)
    tr, tp, tm, dn = r["traduccion"], r["tipo"], r["tamano"], r["donde"]
    db.guardar_analisis(
        codigo=codigo, proyecto_id=p["id"], ticket_numero=t.ticket_numero,
        idioma_titulo=tr["idioma"]["titulo"], idioma_descripcion=tr["idioma"]["descripcion"],
        traducido=int(tr["traducido"]), tipo=tp["clase"], tipo_probabilidades=tp["probabilidades"],
        tamano=tm["clase"], tamano_probabilidades=tm["probabilidades"], tamano_rango=tm["rango"],
        cortes_usados=tm["cortes"], archivos=[{"archivo": a["archivo"], "puntaje": a["puntaje"]} for a in dn["archivos"]],
        error_donde=dn["error"] or None, modelo_tipo=f"{tp['modelo']} v{tp['version']}",
        modelo_tamano=f"{tm['modelo']} v{tm['version']}", metodo_donde=localizacion.parametros(),
        commit_indexado=(dn.get("indice") or {}).get("commit"), segundos=r["segundos"])
    return {"codigo": codigo, "proyecto": p["nombre"], "nota_html": nota_html(r, codigo, URL_PUBLICA),
            "analisis": r}


@app.get("/api/estado", tags=["API"], summary="Modelos cargados, avisos y proyectos")
def api_estado():
    a = estado["analizador"]
    return {"version": VERSION, "modelos": a.clasificador.fichas, "avisos": _avisos(),
            "segundos_carga": round(a.segundos_carga, 1),
            "proyectos": [{"id": p["id"], "nombre": p["nombre"], "estado": p["estado"]}
                          for p in estado["db"].proyectos()]}


# ================================================================ Aceptar / Descartar
ACCIONES = {"aceptar": "aceptado", "descartar": "descartado"}


@app.get("/decision/{codigo}/{accion}", response_class=HTMLResponse, include_in_schema=False)
def ver_decision(request: Request, codigo: str, accion: str):
    a = estado["db"].analisis_por_codigo(codigo)
    if a is None or accion not in ACCIONES:
        raise HTTPException(404, "Enlace no válido.")
    return plantillas.TemplateResponse(request, "decision.html",
                                       {"a": a, "accion": accion, "decision": ACCIONES[accion], "hecho": False})


@app.post("/decision/{codigo}/{accion}", response_class=HTMLResponse, include_in_schema=False)
def guardar_decision(request: Request, codigo: str, accion: str):
    a = estado["db"].analisis_por_codigo(codigo)
    if a is None or accion not in ACCIONES:
        raise HTTPException(404, "Enlace no válido.")
    estado["db"].decidir(codigo, ACCIONES[accion])
    return plantillas.TemplateResponse(request, "decision.html",
                                       {"a": estado["db"].analisis_por_codigo(codigo), "accion": accion,
                                        "decision": ACCIONES[accion], "hecho": True})
