"""Cliente mínimo de la API de Gemini (texto e imágenes) por REST.

Los nombres de modelo cambian seguido, así que si config.json no fija uno,
se elige automáticamente el más nuevo disponible para tu clave.
"""
import base64
import json
import os
import re
import time

import requests

BASE = "https://generativelanguage.googleapis.com/v1beta"
_EXCLUIR_TEXTO = ("image", "tts", "live", "audio", "embedding", "lite", "native",
                  "thinking-exp", "learnlm", "gemma", "robotics", "computer-use")


class GeminiError(RuntimeError):
    pass


def _clave():
    k = os.environ.get("GEMINI_API_KEY")
    if not k:
        raise GeminiError("Falta la variable GEMINI_API_KEY (tu clave de Google AI Studio).")
    return k


def _version(nombre):
    """'models/gemini-3.1-flash-image-preview' -> (3, 1, estable?)"""
    m = re.search(r"gemini-(\d+)(?:\.(\d+))?", nombre)
    if not m:
        return (0, 0, 0)
    estable = 0 if ("preview" in nombre or "exp" in nombre) else 1
    return (int(m.group(1)), int(m.group(2) or 0), estable)


def listar_modelos():
    r = requests.get(f"{BASE}/models", params={"pageSize": 1000},
                     headers={"x-goog-api-key": _clave()}, timeout=60)
    if r.status_code != 200:
        raise GeminiError(f"No pude listar modelos ({r.status_code}): {r.text[:400]}")
    return [m for m in r.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])]


def elegir_modelos(cfg):
    """Devuelve (modelo_texto, modelo_imagen)."""
    texto, imagen = cfg.get("gemini_texto"), cfg.get("gemini_imagen")
    if texto and imagen:
        return texto, imagen
    nombres = [m["name"].replace("models/", "") for m in listar_modelos()]
    if not texto:
        c = [n for n in nombres if "flash" in n and not any(x in n for x in _EXCLUIR_TEXTO)
             and not re.search(r"-\d{3}$|-\d{2}-\d{2}", n)]
        c = c or [n for n in nombres if "flash" in n and not any(x in n for x in _EXCLUIR_TEXTO)]
        if not c:
            raise GeminiError("No encontré un modelo Gemini Flash de texto para tu clave.")
        texto = max(c, key=_version)
    if not imagen:
        c = [n for n in nombres if "flash-image" in n]
        c = c or [n for n in nombres if "image" in n and "gemini" in n]
        if not c:
            raise GeminiError("No encontré un modelo de imágenes (Nano Banana) para tu clave.")
        imagen = max(c, key=_version)
    return texto, imagen


def _post(modelo, cuerpo, intentos=4):
    url = f"{BASE}/models/{modelo}:generateContent"
    espera = 5
    for i in range(intentos):
        r = requests.post(url, json=cuerpo, timeout=240,
                          headers={"x-goog-api-key": _clave(),
                                   "Content-Type": "application/json"})
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504) and i < intentos - 1:
            time.sleep(espera)
            espera *= 2
            continue
        raise GeminiError(f"Gemini {modelo} respondió {r.status_code}: {r.text[:600]}")


def _texto_de(resp):
    partes = resp.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in partes if not p.get("thought"))


def extraer_json(texto):
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", texto, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def generar_json(modelo, instrucciones, prompt, buscar=False, temperatura=0.9):
    """Pide una respuesta JSON. Con buscar=True usa Google Search para verificar datos."""
    cuerpo = {
        "systemInstruction": {"parts": [{"text": instrucciones}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperatura},
    }
    if buscar:
        cuerpo["tools"] = [{"google_search": {}}]
    else:
        cuerpo["generationConfig"]["responseMimeType"] = "application/json"
    try:
        resp = _post(modelo, cuerpo)
    except GeminiError:
        if not buscar:
            raise
        return generar_json(modelo, instrucciones, prompt, buscar=False, temperatura=temperatura)
    texto = _texto_de(resp)
    try:
        return extraer_json(texto)
    except (json.JSONDecodeError, ValueError):
        # Segundo intento pidiendo solo JSON
        cuerpo["contents"].append({"role": "model", "parts": [{"text": texto}]})
        cuerpo["contents"].append({"role": "user", "parts": [{"text":
                                   "Devuelve exclusivamente el JSON válido, sin texto extra."}]})
        cuerpo.pop("tools", None)
        cuerpo["generationConfig"]["responseMimeType"] = "application/json"
        return extraer_json(_texto_de(_post(modelo, cuerpo)))


def generar_imagen(modelo, prompt, destino, tamano="1K", intentos=3):
    cuerpo = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": "9:16", "imageSize": tamano},
        },
    }
    motivo = "sin imagen"
    for i in range(intentos):
        try:
            resp = _post(modelo, cuerpo)
        except GeminiError as e:
            # Algunos modelos no aceptan imageSize: reintenta sin él
            if "imageSize" in str(e) or "image_size" in str(e):
                cuerpo["generationConfig"]["imageConfig"].pop("imageSize", None)
                continue
            raise
        for cand in resp.get("candidates", []):
            for p in cand.get("content", {}).get("parts", []):
                datos = p.get("inlineData") or p.get("inline_data")
                if datos and datos.get("data"):
                    with open(destino, "wb") as f:
                        f.write(base64.b64decode(datos["data"]))
                    return destino
        motivo = resp.get("candidates", [{}])[0].get("finishReason", "sin imagen")
        prompt_suave = prompt + " Family-friendly, non-violent depiction."
        cuerpo["contents"][0]["parts"][0]["text"] = prompt_suave
        time.sleep(3)
    raise GeminiError(f"No se generó la imagen ({motivo}).")
