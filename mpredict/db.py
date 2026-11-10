# -*- coding: utf-8 -*-
"""
Base de datos SQLite de mpredict (datos/mpredict.sqlite).

Solo guarda:
  - proyectos: nombre, URL, carpetas, cortes, índice, tema de osTicket y estado;
  - analisis: qué se predijo para cada ticket, con qué modelos, y la decisión
    (aceptado / descartado).
NO guarda el texto de los tickets, ni nombres, ni correos: eso vive en osTicket.
"""
import datetime
import json
import os
import sqlite3
from contextlib import contextmanager
from zoneinfo import ZoneInfo

ESQUEMA = """
CREATE TABLE IF NOT EXISTS proyectos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    carpeta_repo TEXT,
    rama TEXT,
    commit_actual TEXT,
    carpetas_propuestas TEXT,      -- JSON {carpeta: [motivos]}
    carpetas_disponibles TEXT,     -- JSON [carpetas de primer nivel]
    carpetas TEXT,                 -- JSON [carpetas confirmadas]
    cortes TEXT,                   -- JSON (cortes.calcular_cortes)
    indice TEXT,                   -- carpeta del índice M92
    indice_info TEXT,              -- JSON (meta del índice)
    osticket_tema_id INTEGER,
    osticket_tema_nombre TEXT,
    osticket_mensaje TEXT,
    estado TEXT NOT NULL,          -- descargando | por_confirmar | preparando | listo | listo_con_aviso | error
    mensaje TEXT,
    creado TEXT NOT NULL,
    actualizado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analisis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,   -- código aleatorio de los enlaces Aceptar / Descartar
    proyecto_id INTEGER NOT NULL REFERENCES proyectos(id),
    ticket_numero TEXT,
    creado TEXT NOT NULL,
    idioma_titulo TEXT,
    idioma_descripcion TEXT,
    traducido INTEGER,
    tipo TEXT,
    tipo_probabilidades TEXT,      -- JSON
    tamano TEXT,
    tamano_probabilidades TEXT,    -- JSON
    tamano_rango TEXT,
    cortes_usados TEXT,            -- JSON
    archivos TEXT,                 -- JSON [{archivo, puntaje}]
    error_donde TEXT,
    modelo_tipo TEXT,              -- nombre y versión
    modelo_tamano TEXT,
    metodo_donde TEXT,             -- JSON (parámetros de M92)
    commit_indexado TEXT,
    segundos REAL,
    decision TEXT,                 -- NULL | aceptado | descartado
    fecha_decision TEXT
);
"""

JSON_PROYECTO = ("carpetas_propuestas", "carpetas_disponibles", "carpetas", "cortes", "indice_info")
JSON_ANALISIS = ("tipo_probabilidades", "tamano_probabilidades", "cortes_usados", "archivos", "metodo_donde")


# Hora local para los registros (el contenedor usa UTC). La zona sale de MPREDICT_ZONA;
# la base de zonas horarias viene del paquete tzdata de requirements.txt.
ZONA = ZoneInfo(os.environ.get("MPREDICT_ZONA", "America/Lima"))


def ahora():
    return datetime.datetime.now(ZONA).replace(tzinfo=None).isoformat(timespec="seconds")


class BaseDatos:
    def __init__(self, ruta):
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        self.ruta = ruta
        with self.conexion() as c:
            c.executescript(ESQUEMA)

    @contextmanager
    def conexion(self):
        c = sqlite3.connect(self.ruta, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    @staticmethod
    def _fila(fila, campos_json):
        if fila is None:
            return None
        d = dict(fila)
        for k in campos_json:
            if d.get(k):
                d[k] = json.loads(d[k])
        return d

    # ---------------------------------------------------------- proyectos
    def crear_proyecto(self, nombre, url):
        with self.conexion() as c:
            cur = c.execute("INSERT INTO proyectos (nombre, url, estado, creado, actualizado) "
                            "VALUES (?, ?, 'descargando', ?, ?)", (nombre, url, ahora(), ahora()))
            return cur.lastrowid

    def actualizar_proyecto(self, pid, **campos):
        for k in JSON_PROYECTO:
            if k in campos and campos[k] is not None:
                campos[k] = json.dumps(campos[k], ensure_ascii=False)
        campos["actualizado"] = ahora()
        asignaciones = ", ".join(f"{k} = ?" for k in campos)
        with self.conexion() as c:
            c.execute(f"UPDATE proyectos SET {asignaciones} WHERE id = ?", (*campos.values(), pid))

    def proyecto(self, pid):
        with self.conexion() as c:
            return self._fila(c.execute("SELECT * FROM proyectos WHERE id = ?", (pid,)).fetchone(), JSON_PROYECTO)

    def proyectos(self):
        with self.conexion() as c:
            return [self._fila(f, JSON_PROYECTO) for f in c.execute("SELECT * FROM proyectos ORDER BY id")]

    def proyecto_por_nombre(self, nombre):
        with self.conexion() as c:
            return self._fila(c.execute("SELECT * FROM proyectos WHERE lower(nombre) = lower(?)",
                                        (nombre,)).fetchone(), JSON_PROYECTO)

    def proyecto_por_tema(self, tema_id=None, tema_nombre=None):
        with self.conexion() as c:
            fila = None
            if tema_id:
                fila = c.execute("SELECT * FROM proyectos WHERE osticket_tema_id = ?", (tema_id,)).fetchone()
            if fila is None and tema_nombre:
                fila = c.execute("SELECT * FROM proyectos WHERE osticket_tema_nombre = ? OR "
                                 "'Proyecto ' || nombre = ?", (tema_nombre, tema_nombre)).fetchone()
            return self._fila(fila, JSON_PROYECTO)

    # ---------------------------------------------------------- análisis
    def guardar_analisis(self, **campos):
        for k in JSON_ANALISIS:
            if k in campos and campos[k] is not None:
                campos[k] = json.dumps(campos[k], ensure_ascii=False)
        campos.setdefault("creado", ahora())
        with self.conexion() as c:
            cur = c.execute(f"INSERT INTO analisis ({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})",
                            tuple(campos.values()))
            return cur.lastrowid

    def analisis_por_codigo(self, codigo):
        with self.conexion() as c:
            return self._fila(c.execute("SELECT a.*, p.nombre AS proyecto FROM analisis a JOIN proyectos p "
                                        "ON p.id = a.proyecto_id WHERE codigo = ?", (codigo,)).fetchone(),
                              JSON_ANALISIS)

    def decidir(self, codigo, decision):
        with self.conexion() as c:
            c.execute("UPDATE analisis SET decision = ?, fecha_decision = ? WHERE codigo = ?",
                      (decision, ahora(), codigo))
