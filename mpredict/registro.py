# -*- coding: utf-8 -*-
"""
Registro y actualización de proyectos, EN SEGUNDO PLANO (un trabajo a la vez).

Estados:
  descargando   -> clonando (o actualizando) el repositorio
  por_confirmar -> carpetas de código propuestas; espera que el administrador las confirme
  preparando    -> cortes de tamaño, índice de M92 y tema de osTicket
  listo / listo_con_aviso (cortes con pocos commits) / error (con mensaje)
"""
import os
import re
import traceback
from concurrent.futures import ThreadPoolExecutor

from . import cortes, localizacion, osticket, repos

_TRABAJOS = ThreadPoolExecutor(max_workers=1, thread_name_prefix="registro")
EN_CURSO = ("descargando", "preparando")
RE_NOMBRE = re.compile(r"^[\w .()+-]{1,60}$", re.UNICODE)


class Registro:
    def __init__(self, db, cfg):
        self.db, self.cfg = db, cfg
        # Si mpredict se apagó con un trabajo a medias, ese proyecto queda en error
        for p in db.proyectos():
            if p["estado"] in EN_CURSO:
                db.actualizar_proyecto(p["id"], estado="error",
                                       mensaje="Se interrumpió al apagarse mpredict. Pulsa «Actualizar».")

    def _carpeta_repo(self, pid):
        return os.path.join(self.cfg["datos"], "repos", str(pid))

    def _carpeta_indice(self, pid):
        return os.path.join(self.cfg["datos"], "indices", str(pid))

    def _en_fondo(self, pid, funcion, *args):
        def trabajo():
            try:
                funcion(pid, *args)
            except Exception as e:
                traceback.print_exc()
                self.db.actualizar_proyecto(pid, estado="error", mensaje=f"{type(e).__name__}: {e}")
        _TRABAJOS.submit(trabajo)

    # ------------------------------------------------------------ acciones
    def registrar(self, nombre, url):
        nombre = (nombre or "").strip()
        if not RE_NOMBRE.match(nombre):
            raise ValueError("El nombre debe tener entre 1 y 60 caracteres (letras, números, espacios, . ( ) + -).")
        url = repos.validar_url(url)
        if self.db.proyecto_por_nombre(nombre):
            raise ValueError(f"Ya existe un proyecto llamado «{nombre}».")
        pid = self.db.crear_proyecto(nombre, url)
        self._en_fondo(pid, self._descargar)
        return pid

    def confirmar(self, pid, carpetas):
        p = self.db.proyecto(pid)
        carpetas = [c for c in carpetas if c in (p.get("carpetas_disponibles") or [])]
        if not carpetas:
            raise ValueError("Marca al menos una carpeta de código.")
        self.db.actualizar_proyecto(pid, carpetas=carpetas, estado="preparando",
                                    mensaje="Calculando cortes e índice...")
        self._en_fondo(pid, self._preparar)

    def actualizar(self, pid):
        p = self.db.proyecto(pid)
        if p["estado"] in EN_CURSO:
            raise ValueError("El proyecto ya tiene un trabajo en curso.")
        self.db.actualizar_proyecto(pid, estado="descargando", mensaje="Trayendo los cambios...")
        self._en_fondo(pid, self._actualizar)

    # ------------------------------------------------------------ trabajos
    def _descargar(self, pid):
        p = self.db.proyecto(pid)
        destino = self._carpeta_repo(pid)
        if os.path.isdir(os.path.join(destino, ".git")):
            rama = repos.actualizar(destino)
        else:
            self.db.actualizar_proyecto(pid, mensaje="Clonando el repositorio (historial completo)...")
            rama = repos.clonar(p["url"], destino)
        self.db.actualizar_proyecto(
            pid, carpeta_repo=destino, rama=rama, commit_actual=repos.commit_actual(destino),
            carpetas_propuestas=repos.detectar_carpetas(destino),
            carpetas_disponibles=repos.carpetas_de_primer_nivel(destino),
            estado="por_confirmar", mensaje="Confirma las carpetas de código.")

    def _actualizar(self, pid):
        p = self.db.proyecto(pid)
        destino = self._carpeta_repo(pid)
        if not p.get("carpetas") or not os.path.isdir(os.path.join(destino, ".git")):
            return self._descargar(pid)          # nunca llegó a prepararse: se empieza de nuevo
        rama = repos.actualizar(destino)
        self.db.actualizar_proyecto(pid, rama=rama, commit_actual=repos.commit_actual(destino),
                                    carpetas_propuestas=repos.detectar_carpetas(destino),
                                    carpetas_disponibles=repos.carpetas_de_primer_nivel(destino),
                                    estado="preparando", mensaje="Calculando cortes e índice...")
        self._preparar(pid)

    def _preparar(self, pid):
        p = self.db.proyecto(pid)
        repo, carpetas = p["carpeta_repo"], p["carpetas"]
        self.db.actualizar_proyecto(pid, mensaje="Calculando los cortes de tamaño...")
        c = cortes.calcular_cortes(repo, "HEAD", carpetas)
        self.db.actualizar_proyecto(pid, cortes=c, mensaje="Construyendo el índice de M92...")
        fc = localizacion.fragmentos_de_carpetas(repo, carpetas)
        if not fc:
            raise ValueError("Las carpetas confirmadas no tienen archivos .py (sin contar pruebas ni migraciones).")
        meta = localizacion.construir_indice(fc, self._carpeta_indice(pid),
                                             {"commit": p["commit_actual"], "carpetas": carpetas})
        tema_id, tema_nombre, tema_msg = p.get("osticket_tema_id"), p.get("osticket_tema_nombre"), ""
        if not tema_id:
            try:
                t = osticket.crear_tema(p["nombre"])
                if t:
                    tema_id, tema_nombre = t["id"], t["nombre"]
                else:
                    tema_msg = "pendiente: osTicket no está configurado"
            except Exception as e:
                tema_msg = f"no se pudo crear: {e}"
        estado = "listo" if c["estado"] == "normal" else "listo_con_aviso"
        self.db.actualizar_proyecto(pid, indice=self._carpeta_indice(pid), indice_info=meta,
                                    osticket_tema_id=tema_id, osticket_tema_nombre=tema_nombre,
                                    osticket_mensaje=tema_msg, estado=estado, mensaje=c.get("aviso", ""))
