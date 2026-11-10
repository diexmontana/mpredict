# -*- coding: utf-8 -*-
"""
Nota interna «Análisis mpredict» en HTML y en español.

La escribe mpredict (no el complemento) para poder probarla sin osTicket: el
complemento solo la pega en el ticket. Incluye los avisos de honestidad:
tamaño de baja confianza, M92 es una reconstrucción y solo analiza .py,
y los enlaces Aceptar / Descartar con el código único del análisis.
"""
from html import escape


# Tipos de mantenimiento de la norma ISO/IEC 14764 (ver DATASETS_MODELOS_Y_DECISIONES.md, 2.1).
# El modelo responde con las etiquetas de sus datos; se muestran como «Correctivo (Bug)».
TIPOS_ES = {"Bug": "Correctivo", "New feature": "Perfectivo", "Cleanup/optimization": "Preventivo"}


def tipo_es(etiqueta):
    """«Bug» -> «Correctivo (Bug)». Una etiqueta sin equivalencia se muestra tal cual."""
    return f"{TIPOS_ES[etiqueta]} ({etiqueta})" if etiqueta in TIPOS_ES else etiqueta


def _pct(x):
    return f"{round(x * 100)} %"


def nota_html(r, codigo, url_publica):
    tr, tp, tm, dn = r["traduccion"], r["tipo"], r["tamano"], r["donde"]
    h = []
    if tr["traducido"]:
        desc = tr["descripcion"]
        desc = desc if len(desc) <= 800 else desc[:800] + "…"
        h.append("<p><b>Traducción al inglés</b> (automática, con opus-mt-es-en; puede contener errores):<br>"
                 f"<i>{escape(tr['titulo'])}</i><br><small>{escape(desc).replace(chr(10), '<br>')}</small></p>")
    h.append("<p><b>Tipo de mantenimiento:</b> " + " · ".join(
        (f"<b>{escape(tipo_es(p['clase']))} {_pct(p['probabilidad'])}</b>" if i == 0
         else f"{escape(tipo_es(p['clase']))} {_pct(p['probabilidad'])}") for i, p in enumerate(tp["probabilidades"])) + "</p>")
    rango = f" — {escape(tm['rango'])} en este proyecto" if tm["rango"] else ""
    h.append(f"<p><b>Tamaño del cambio:</b> <b>{escape(tm['clase'])}</b>{rango} "
             f"({_pct(tm['probabilidades'][0]['probabilidad'])}). "
             + " · ".join(f"{escape(p['clase'])} {_pct(p['probabilidad'])}" for p in tm["probabilidades"])
             + f"<br><small>⚠ {escape(tm['aviso'])}"
             + (f" {escape(tm['aviso_cortes'])}" if tm["aviso_cortes"] else "") + "</small></p>")
    h.append("<p><b>Dónde — 5 archivos Python candidatos:</b></p>")
    if dn["error"]:
        h.append(f"<p>No se pudo calcular: {escape(dn['error'])}</p>")
    else:
        h.append("<ol>" + "".join(f"<li><code>{escape(a['archivo'])}</code> (puntaje {a['puntaje']:.4f})</li>"
                                  for a in dn["archivos"]) + "</ol>")
        commit = (dn.get("indice") or {}).get("commit") or ""
        h.append(f"<p><small>⚠ {escape(dn['aviso'])} Se busca en el código del proyecto en el commit "
                 f"{escape(commit[:8])}: si un arreglo ya está en ese código, que aparezca su archivo no "
                 f"demuestra un acierto.</small></p>")
    base = url_publica.rstrip("/")
    h.append(f"<p><b>¿Te sirve este análisis?</b> "
             f"<a href=\"{base}/decision/{codigo}/aceptar\">Aceptar</a> · "
             f"<a href=\"{base}/decision/{codigo}/descartar\">Descartar</a> "
             f"<small>(se pedirá confirmación)</small></p>")
    h.append(f"<p><small>Generado por mpredict en {r['segundos']:.1f} s. Modelos: {escape(tp['modelo'] or '')} "
             f"v{escape(str(tp['version']))} y {escape(tm['modelo'] or '')} v{escape(str(tm['version']))}. "
             "Es una primera lectura: revísala antes de decidir.</small></p>")
    return "\n".join(h)
