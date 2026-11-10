# -*- coding: utf-8 -*-
"""
Traducción español -> inglés del título y la descripción de un ticket.

Pasos, para cada campo por separado:
  1. PROTEGER: el código se sustituye por marcadores (ZXQ0, ZXQ1, ...): bloques
     ``` / ~~~ / {{{ }}}, tracebacks completos, `código en línea`, URLs, rutas de
     archivos y nombres técnicos (QuerySet.filter(), __init__, snake_case, CamelCase).
  2. DETECTAR el idioma sobre el texto SIN código (lingua, solo español/inglés).
     Si no es español, el campo se deja tal cual.
  3. TRADUCIR con Helsinki-NLP/opus-mt-es-en, línea por línea (las líneas largas se
     parten en frases: el modelo admite como máximo 512 fragmentos de palabra).
  4. RESTAURAR los marcadores y comprobar que todos volvieron intactos. Si el modelo
     deformó alguno, se traduce de nuevo esa línea por trozos: solo el texto que hay
     entre las partes protegidas, sin enviar nunca el código al modelo.
"""
import re

MODELO_TRADUCCION = "Helsinki-NLP/opus-mt-es-en"
MARCA = "ZXQ{}"
RE_MARCA = re.compile(r"ZXQ(\d+)")

# --- protección: bloques de varias líneas
RE_VALLA = re.compile(r"(?ms)^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*$")
RE_TRAC = re.compile(r"(?s)\{\{\{.*?\}\}\}")
# --- protección: dentro de una línea (en este orden)
EN_LINEA = [
    re.compile(r"`[^`\n]+`"),                                              # `código`
    re.compile(r"https?://\S+"),                                           # URL
    re.compile(r"(?:\./|\b)(?:[\w.-]+/)+[\w-]+\.\w+\b"),                   # ruta/con/archivo.py
    re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+(?:\([^()\n]*\))?"),     # QuerySet.filter()
    re.compile(r"\b[A-Za-z_]\w*\([^()\n]*\)"),                             # funcion()
    re.compile(r"\b__\w+__\b"),                                            # __init__
    re.compile(r"\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+\b"),                     # snake_case
    re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b"),                  # CamelCase
    re.compile(r"\b[a-z]+[A-Z]\w*\b"),                                     # camelCase
]
RE_FRASES = re.compile(r"(?<=[.!?;:])\s+")
RE_LETRAS = re.compile(r"[^\W\d_]{2,}")


# =====================================================================
# 1. Proteger y restaurar
# =====================================================================
def _bloques_traceback(texto, guardar):
    """Desde «Traceback (most recent call last):» hasta la línea del error (la primera sin sangría)."""
    lineas, salida, i = texto.split("\n"), [], 0
    while i < len(lineas):
        if "Traceback (most recent call last)" in lineas[i]:
            j = i + 1
            while j < len(lineas) and (lineas[j].startswith((" ", "\t")) or not lineas[j].strip()):
                j += 1
            fin = min(j, len(lineas) - 1)
            salida.append(guardar("\n".join(lineas[i:fin + 1])))
            i = fin + 1
        else:
            salida.append(lineas[i])
            i += 1
    return "\n".join(salida)


def proteger(texto):
    """Devuelve (texto con marcadores, lista de trozos protegidos)."""
    trozos = []

    def guardar(t):
        trozos.append(t)
        return MARCA.format(len(trozos) - 1)

    t = RE_VALLA.sub(lambda m: guardar(m.group(0)), texto or "")
    t = RE_TRAC.sub(lambda m: guardar(m.group(0)), t)
    t = _bloques_traceback(t, guardar)
    for patron in EN_LINEA:
        t = patron.sub(lambda m: m.group(0) if RE_MARCA.fullmatch(m.group(0)) else guardar(m.group(0)), t)
    return t, trozos


def restaurar(texto, trozos):
    return RE_MARCA.sub(lambda m: trozos[int(m.group(1))] if int(m.group(1)) < len(trozos) else m.group(0), texto)


def marcas_intactas(original, traducido):
    """¿Aparecen en la traducción exactamente los mismos marcadores?"""
    return sorted(RE_MARCA.findall(original)) == sorted(RE_MARCA.findall(traducido))


# =====================================================================
# 2. Traductor
# =====================================================================
class Traductor:
    def __init__(self):
        from lingua import Language, LanguageDetectorBuilder
        from transformers import MarianMTModel, MarianTokenizer
        self._es = Language.SPANISH
        self.detector = LanguageDetectorBuilder.from_languages(Language.ENGLISH, Language.SPANISH).build()
        self.tok = MarianTokenizer.from_pretrained(MODELO_TRADUCCION, local_files_only=True)
        self.modelo = MarianMTModel.from_pretrained(MODELO_TRADUCCION, local_files_only=True)
        self.modelo.eval()

    # ---------------------------------------------------- idioma
    def idioma(self, texto_con_marcas):
        """'es', 'en' o '' (sin texto que analizar), sobre el texto SIN código."""
        limpio = RE_MARCA.sub(" ", texto_con_marcas)
        if not RE_LETRAS.search(limpio):
            return ""
        lang = self.detector.detect_language_of(limpio)
        if lang is None:
            return "es" if re.search(r"[ñáéíóú¿¡]", limpio, re.I) else "en"
        return "es" if lang == self._es else "en"

    # ---------------------------------------------------- modelo
    def _modelo(self, frases):
        """Traduce una lista de frases (en lotes de 8)."""
        import torch
        salida = []
        for k in range(0, len(frases), 8):
            lote = frases[k:k + 8]
            entrada = self.tok(lote, return_tensors="pt", padding=True, truncation=True, max_length=512)
            with torch.no_grad():
                gen = self.modelo.generate(**entrada)   # máx. 512 (generation_config del modelo)
            salida += [self.tok.decode(g, skip_special_tokens=True) for g in gen]
        return salida

    def _partes(self, linea):
        """Una línea larga -> frases que caben en el modelo."""
        if len(self.tok(linea)["input_ids"]) <= 400:
            return [linea]
        return [f for f in RE_FRASES.split(linea) if f.strip()]

    def _traducir_linea(self, linea):
        """Devuelve (traducción, método)."""
        if not RE_LETRAS.search(RE_MARCA.sub(" ", linea)):
            return linea, "sin_texto"                       # solo código, números o vacía
        sangria = linea[:len(linea) - len(linea.lstrip())]
        partes = self._partes(linea.strip())
        trad = " ".join(self._modelo(partes))
        if marcas_intactas(linea, trad):
            return sangria + trad, "marcadores"
        # Plan B: traducir solo el texto entre marcadores
        trozos = re.split(r"(ZXQ\d+)", linea.strip())
        textos = [i for i, t in enumerate(trozos) if not RE_MARCA.fullmatch(t) and RE_LETRAS.search(t)]
        if textos:
            hechas = self._modelo([trozos[i].strip() for i in textos])
            for i, h in zip(textos, hechas):
                izq = " " if trozos[i][:1].isspace() else ""
                der = " " if trozos[i][-1:].isspace() else ""
                trozos[i] = izq + h + der
        return sangria + "".join(trozos), "segmentos"

    # ---------------------------------------------------- público
    def traducir_campo(self, texto):
        """{'texto': inglés, 'idioma': 'es'|'en'|'', 'traducido': bool, 'metodos': [...]}"""
        con_marcas, trozos = proteger(texto or "")
        idioma = self.idioma(con_marcas)
        if idioma != "es":
            return {"texto": texto or "", "idioma": idioma, "traducido": False, "metodos": []}
        lineas, metodos = [], set()
        for linea in con_marcas.split("\n"):
            t, m = self._traducir_linea(linea)
            lineas.append(t)
            metodos.add(m)
        metodos.discard("sin_texto")
        return {"texto": restaurar("\n".join(lineas), trozos), "idioma": "es", "traducido": True,
                "metodos": sorted(metodos)}

    def traducir_ticket(self, titulo, descripcion):
        t, d = self.traducir_campo(titulo), self.traducir_campo(descripcion)
        return {"titulo": t["texto"], "descripcion": d["texto"],
                "idioma": {"titulo": t["idioma"], "descripcion": d["idioma"]},
                "traducido": t["traducido"] or d["traducido"],
                "metodos": sorted(set(t["metodos"]) | set(d["metodos"]))}
