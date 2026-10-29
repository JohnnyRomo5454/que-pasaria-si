"""Cliente mínimo de la API de OpenAI (texto con búsqueda web e imágenes) por REST.

Mismas funciones que gemini.py para poder cambiar de proveedor en config.json.
Si config no fija modelos, se eligen automáticamente según lo que tu cuenta tenga.
"""
import base64
import json
import os
import re
import time

import requests

BASE = "https://api.openai.com/v1"
_EXCLUIR_TEXTO = ("image", "audio", "realtime", "tts", "transcribe", "search", "embedding",
                  "codex", "oss", "moderation", "instruct", "dall-e", "whisper", "chat-latest",
                  "deep-research", "computer", "nano", "pro")


class OpenAIError(RuntimeError):
    pass


def _cab():
    k = os.environ.get("OPENAI_API_KEY")
    if not k:
        raise OpenAIError("Falta la variable OPENAI_API_KEY.")
    return {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}


def _version(nombre):
    m = re.search(r"gpt-(?:image-)?(\d+)(?:\.(\d+))?", nombre)
    if not m:
        return (0, 0, 0)
    sin_fecha = 0 if re.search(r"\d{4}-\d{2}-\d{2}", nombre) else 1
    return (int(m.group(1)), int(m.group(2) or 0), sin_fecha)


def listar_modelos():
    r = requests.get(f"{BASE}/models", headers=_cab(), timeout=60)
    if r.status_code != 200:
        raise OpenAIError(f"No pude listar modelos ({r.status_code}): {r.text[:400]}")
    return [m["id"] for m in r.json().get("data", [])]


def candidatos_imagen(ids):
    c = [i for i in ids if "gpt-image" in i and not re.search(r"\d{4}-\d{2}-\d{2}", i)]
    # Preferir el modelo "rápido/diario" más nuevo y luego el resto, del más nuevo al más viejo
    return sorted(c, key=lambda n: (("flare" in n or "mini" in n), _version(n)), reverse=True)


def elegir_modelos(cfg):
    texto, imagen = cfg.get("openai_texto"), cfg.get("openai_imagen")
    if texto and imagen:
        return texto, imagen
    ids = listar_modelos()
    if not texto:
        base = [i for i in ids if i.startswith("gpt-") and not any(x in i for x in _EXCLUIR_TEXTO)
                and not re.search(r"\d{4}-\d{2}-\d{2}", i)]
        minis = [i for i in base if "mini" in i]
        c = minis or base
        if not c:
            raise OpenAIError("No encontré un modelo de texto GPT en tu cuenta.")
        texto = max(c, key=_version)
    if not imagen:
        c = candidatos_imagen(ids)
        if not c:
            raise OpenAIError("Tu cuenta no tiene modelos de imagen GPT Image disponibles.")
        imagen = c[0]
    return texto, imagen


def _post(ruta, cuerpo, intentos=4):
    espera = 5
    for i in range(intentos):
        r = requests.post(f"{BASE}/{ruta}", json=cuerpo, headers=_cab(), timeout=300)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504) and i < intentos - 1 \
                and "insufficient_quota" not in r.text:
            time.sleep(espera)
            espera *= 2
            continue
        if "insufficient_quota" in r.text:
            raise OpenAIError("Se acabó el saldo de OpenAI. Recarga en platform.openai.com → Billing.")
        raise OpenAIError(f"OpenAI {ruta} respondió {r.status_code}: {r.text[:600]}")


def _texto_de(resp):
    partes = []
    for item in resp.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") in ("output_text", "text"):
                    partes.append(c.get("text", ""))
    return "".join(partes) or resp.get("output_text", "")


def extraer_json(texto):
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip())
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", texto, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def generar_json(modelo, instrucciones, prompt, buscar=False, temperatura=None):
    """Respuesta en JSON. Con buscar=True el modelo puede consultar la web."""
    cuerpo = {"model": modelo, "instructions": instrucciones + "\nResponde solo con JSON válido.",
              "input": prompt}
    if buscar:
        cuerpo["tools"] = [{"type": "web_search"}]
    else:
        cuerpo["text"] = {"format": {"type": "json_object"}}
    try:
        resp = _post("responses", cuerpo)
    except OpenAIError:
        if not buscar:
            raise
        return generar_json(modelo, instrucciones, prompt, buscar=False)
    texto = _texto_de(resp)
    try:
        return extraer_json(texto)
    except (json.JSONDecodeError, ValueError):
        cuerpo.pop("tools", None)
        cuerpo["text"] = {"format": {"type": "json_object"}}
        cuerpo["input"] = prompt + "\n\nTu respuesta anterior no era JSON válido:\n" + texto[:4000]
        return extraer_json(_texto_de(_post("responses", cuerpo)))


_imagen_ok = {}


def generar_imagen(modelo, prompt, destino, tamano="1024x1536", intentos=2):
    """Genera una imagen vertical. Si tu cuenta no tiene acceso al modelo elegido
    (por ejemplo, por verificación de organización), prueba con los demás disponibles."""
    modelos = [_imagen_ok.get("m", modelo)]
    ultimo = None
    for m in modelos + [x for x in candidatos_imagen(listar_modelos()) if x not in modelos]:
        for i in range(intentos):
            try:
                resp = _post("images/generations", {"model": m, "prompt": prompt, "n": 1,
                                                    "size": tamano, "quality": "medium"})
            except OpenAIError as e:
                ultimo = e
                txt = str(e).lower()
                if "verif" in txt or "403" in txt or "model_not_found" in txt or "does not exist" in txt:
                    break                       # probar el siguiente modelo
                if "safety" in txt or "moderation" in txt:
                    prompt += " Family-friendly, non-violent, no gore."
                    continue
                raise
            datos = (resp.get("data") or [{}])[0]
            if datos.get("b64_json"):
                with open(destino, "wb") as f:
                    f.write(base64.b64decode(datos["b64_json"]))
                _imagen_ok["m"] = m
                return destino
            if datos.get("url"):
                with open(destino, "wb") as f:
                    f.write(requests.get(datos["url"], timeout=120).content)
                _imagen_ok["m"] = m
                return destino
    msg = str(ultimo)
    if "verif" in msg.lower():
        raise OpenAIError("OpenAI pide verificar tu organización para generar imágenes. Ve a "
                          "platform.openai.com/settings/organization/general → Verify Organization.")
    raise OpenAIError(f"No se pudo generar la imagen: {msg}")
