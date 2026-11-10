# -*- coding: utf-8 -*-
"""
Creación del tema de ayuda «Proyecto <nombre>» en osTicket.

La API de osTicket solo crea tickets. Por eso el complemento mpredict añade a la
API de osTicket la ruta  POST /api/mpredict/tema  (señal 'api', el mecanismo de
osTicket para que un complemento registre rutas). Esa ruta crea el tema con la
propia clase de osTicket (Topic::__create, la que usa su instalador).

Variables de entorno (las fija docker-compose.yml):
  OSTICKET_URL       p. ej. http://mpredict-osticket   (dentro de la red de Docker)
  OSTICKET_SECRETO   el mismo secreto configurado en el complemento (MPREDICT_SECRETO de .env)
Si no están definidas (mpredict fuera de Docker), el tema queda «pendiente».
"""
import json
import os
import urllib.error
import urllib.request


def nombre_tema(nombre_proyecto):
    """osTicket exige 5 caracteres o más: con el prefijo siempre se cumple."""
    return f"Proyecto {nombre_proyecto}"


def configurado():
    return bool(os.environ.get("OSTICKET_URL") and os.environ.get("OSTICKET_SECRETO"))


def crear_tema(nombre_proyecto):
    """Devuelve {'id': ..., 'nombre': ...}, o None si osTicket no está configurado.
    Si el tema ya existe, osTicket devuelve el mismo id (no se duplica)."""
    if not configurado():
        return None
    url = os.environ["OSTICKET_URL"].rstrip("/") + "/api/mpredict/tema"
    datos = json.dumps({"nombre": nombre_tema(nombre_proyecto)}).encode("utf-8")
    pedido = urllib.request.Request(url, data=datos, method="POST", headers={
        "Content-Type": "application/json", "X-Mpredict-Secreto": os.environ["OSTICKET_SECRETO"]})
    try:
        with urllib.request.urlopen(pedido, timeout=20) as r:
            respuesta = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"osTicket respondió {e.code}: {cuerpo}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"no se pudo conectar con osTicket en {url}: {e.reason}") from e
    return {"id": int(respuesta["id"]), "nombre": respuesta["nombre"]}
