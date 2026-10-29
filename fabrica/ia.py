"""Elige el proveedor de IA (texto + imágenes) según config.json → "proveedor"."""
import json
from pathlib import Path

_cfg = json.loads((Path(__file__).resolve().parent.parent / "config.json").read_text(encoding="utf-8"))
PROVEEDOR = _cfg.get("proveedor", "openai")

if PROVEEDOR == "gemini":
    from . import gemini as p
else:
    from . import openai_api as p

elegir_modelos = p.elegir_modelos
generar_json = p.generar_json
generar_imagen = p.generar_imagen
TAMANO_IMAGEN = _cfg.get("imagen_tamano_" + PROVEEDOR, "1024x1536" if PROVEEDOR == "openai" else "1K")
