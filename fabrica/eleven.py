"""Voz con ElevenLabs, incluyendo los tiempos exactos de cada palabra."""
import base64
import os
import re
import time

import requests

BASE = "https://api.elevenlabs.io/v1"


class ElevenError(RuntimeError):
    pass


def _cabeceras():
    k = os.environ.get("ELEVENLABS_API_KEY")
    if not k:
        raise ElevenError("Falta la variable ELEVENLABS_API_KEY.")
    return {"xi-api-key": k, "Content-Type": "application/json"}


def resolver_voz(nombre_o_id):
    """Acepta el ID de la voz o su nombre tal como aparece en 'My Voices'."""
    if re.fullmatch(r"[A-Za-z0-9]{20}", nombre_o_id or ""):
        return nombre_o_id
    r = requests.get(f"{BASE}/voices", headers=_cabeceras(), timeout=60)
    if r.status_code != 200:
        raise ElevenError(f"No pude listar tus voces ({r.status_code}): {r.text[:300]}")
    voces = r.json().get("voices", [])
    buscado = (nombre_o_id or "").lower()
    for v in voces:
        if v.get("name", "").lower() == buscado:
            return v["voice_id"]
    for v in voces:
        if buscado and buscado in v.get("name", "").lower():
            return v["voice_id"]
    nombres = ", ".join(v.get("name", "?") for v in voces)
    raise ElevenError(f"No encontré la voz '{nombre_o_id}' en tu cuenta. Tus voces: {nombres}")


def narrar(texto, voz_id, modelo, ajustes, destino_mp3, idioma=None):
    """Genera el audio y devuelve la lista de palabras con sus tiempos:
    [(palabra, inicio, fin), ...]"""
    cuerpo = {"text": texto, "model_id": modelo, "voice_settings": ajustes}
    if idioma and "multilingual_v2" not in modelo:
        cuerpo["language_code"] = idioma
    espera = 5
    for i in range(4):
        r = requests.post(f"{BASE}/text-to-speech/{voz_id}/with-timestamps",
                          params={"output_format": "mp3_44100_128"},
                          json=cuerpo, headers=_cabeceras(), timeout=300)
        if r.status_code == 200:
            break
        if r.status_code in (429, 500, 502, 503) and i < 3:
            time.sleep(espera)
            espera *= 2
            continue
        raise ElevenError(f"ElevenLabs respondió {r.status_code}: {r.text[:400]}")
    datos = r.json()
    with open(destino_mp3, "wb") as f:
        f.write(base64.b64decode(datos["audio_base64"]))
    al = datos.get("alignment") or datos.get("normalized_alignment")
    return palabras_desde_caracteres(al["characters"],
                                     al["character_start_times_seconds"],
                                     al["character_end_times_seconds"])


def palabras_desde_caracteres(chars, inicios, fines):
    palabras, actual, t0, t1 = [], "", None, None
    for c, s, e in zip(chars, inicios, fines):
        if c.isspace():
            if actual:
                palabras.append((actual, t0, t1))
            actual, t0 = "", None
            continue
        if t0 is None:
            t0 = s
        actual += c
        t1 = e
    if actual:
        palabras.append((actual, t0, t1))
    return palabras
