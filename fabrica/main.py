"""Orquestador: idea → guion → verificación → imágenes → voz → edición.

Uso:
  python -m fabrica.main                       # el sistema elige el tema
  python -m fabrica.main --tema "¿Qué pasaría si la Luna desapareciera?"
  python -m fabrica.main --ideas               # solo propone 10 ideas
  python -m fabrica.main --simulacion          # prueba sin gastar APIs
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from . import editor

RAIZ = Path(__file__).resolve().parent.parent
HISTORIAL = RAIZ / "data" / "historial.json"


def log(msg):
    print(msg, flush=True)


def resumen(md):
    """Escribe en el resumen de la ejecución de GitHub Actions (si existe)."""
    import os
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(md + "\n")


def slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t.lower()).strip("-")
    return t[:60] or "video"


def cargar_historial():
    if HISTORIAL.exists():
        return json.loads(HISTORIAL.read_text(encoding="utf-8"))
    return []


def guardar_historial(h):
    HISTORIAL.parent.mkdir(parents=True, exist_ok=True)
    HISTORIAL.write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")


def contar(guion, idioma):
    return sum(len(e[idioma].split()) for e in guion["escenas"])


# ------------------------------------------------------------- modo simulación

GUION_PRUEBA = {
    "tema": {"es": "¿Qué pasaría si la Luna desapareciera?",
             "en": "What if the Moon disappeared?"},
    "titulo": {"es": "¿Y si la Luna desapareciera esta noche?", "en": "What if the Moon vanished tonight?"},
    "descripcion": {"es": "Prueba del sistema.", "en": "System test."},
    "hashtags": {"es": ["#quepasariasi"], "en": ["#whatif"]},
    "escenas": [
        {"es": "Si la Luna desapareciera esta noche, nadie moriría al instante… pero la Tierra cambiaría para siempre.",
         "en": "If the Moon vanished tonight, no one would die instantly… but Earth would change forever.",
         "imagen": "", "movimiento": "zoom_in"},
        {"es": "Lo primero que notarías es el cielo: noches mucho más oscuras, llenas de estrellas.",
         "en": "The first thing you'd notice is the sky: much darker nights, packed with stars.",
         "imagen": "", "movimiento": "subir"},
        {"es": "Las mareas bajarían a casi un tercio, y miles de especies costeras perderían su hogar.",
         "en": "Tides would shrink to about a third, and thousands of coastal species would lose their home.",
         "imagen": "", "movimiento": "derecha"},
        {"es": "¿Y tú? ¿Qué extrañarías más de la Luna? Te leo en los comentarios.",
         "en": "And you? What would you miss most about the Moon? Tell me in the comments.",
         "imagen": "", "movimiento": "zoom_out"},
    ],
}


def _imagen_prueba(i, destino):
    colores = ["0x1b2a49:0x7a3e9d", "0x0f3d3e:0x3fa796", "0x5c1a1b:0xe08e45", "0x232946:0xb8c1ec"]
    c0, c1 = colores[i % len(colores)].split(":")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"gradients=s=768x1376:c0={c0}:c1={c1}:x0=0:y0=0:x1=768:y1=1376:d=1",
                    "-frames:v", "1", str(destino)], check=True)


def _voz_prueba(texto, destino):
    """Audio de tono suave con tiempos falsos (0.32 s por palabra + pausas)."""
    palabras, t = [], 0.2
    for w in texto.split():
        d = 0.18 + 0.03 * len(w)
        palabras.append((w, t, t + d))
        t += d + (0.35 if re.search(r"[….,?!]$", w) else 0.06)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"sine=frequency=220:duration={t + 0.2}", "-af", "volume=0.05",
                    str(destino)], check=True)
    return palabras


# ------------------------------------------------------------- pasos reales

def conteos(guion):
    return [(len(e["es"].split()), len(e["en"].split())) for e in guion["escenas"]]


def largo_ok(guion, cfg):
    return contar(guion, "es") <= cfg["palabras_es"][1] and contar(guion, "en") <= cfg["palabras_en"][1]


def obtener_guion(mod_texto, tema_es, tema_en, cfg, carpeta):
    from . import agentes
    guion, notas, reporte, aprobado = None, None, [], False
    for vuelta in range(cfg["max_revisiones"] + 1):
        log(f"✍️  Guionista (versión {vuelta + 1})…")
        guion = agentes.escribir_guion(mod_texto, tema_es, tema_en, cfg,
                                       notas=notas,
                                       anterior=json.dumps(guion, ensure_ascii=False) if guion else None)
        for _ in range(2):
            if largo_ok(guion, cfg):
                break
            log(f"✂️  Recortando ({contar(guion, 'es')} palabras ES, {contar(guion, 'en')} EN)…")
            guion = agentes.recortar(mod_texto, json.dumps(guion, ensure_ascii=False), conteos(guion), cfg)
        pes, pen = contar(guion, "es"), contar(guion, "en")
        log(f"🔎 Verificador revisando ({pes} palabras ES, {pen} EN)…")
        rev = agentes.verificar(mod_texto, json.dumps(guion, ensure_ascii=False), pes, pen)
        obligatorios = rev.get("obligatorios") or []
        pts = rev.get("puntajes") or {}
        aprobado = (not obligatorios and pts.get("veracidad", 0) >= 7
                    and pts.get("seguridad", 0) >= 7)
        rev["aprobado"] = aprobado
        reporte.append(rev)
        log(f"   Puntajes: {pts}  obligatorios: {len(obligatorios)}  aprobado: {aprobado}")
        if aprobado:
            break
        notas = "\n".join(f"- {c}" for c in obligatorios) or "- Mejora el gancho y la veracidad."
    if not largo_ok(guion, cfg):
        log("⚠️  El guion sigue largo; se acelerará un poco la voz.")
    (carpeta / "verificacion.json").write_text(json.dumps(reporte, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    return guion, reporte[-1]


def ajustar_velocidad(voz, palabras, maximo):
    """Si la narración pasa del máximo, la acelera hasta un 12% (sin cambiar el tono)."""
    seg = editor.duracion(voz)
    if seg + editor.COLA <= maximo:
        return palabras
    factor = min(1.12, (seg + editor.COLA) / maximo)
    tmp = voz.with_name(voz.stem + "_rapida.mp3")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(voz), "-filter:a",
                    f"atempo={factor:.3f}", str(tmp)], check=True)
    tmp.replace(voz)
    log(f"   ⏩ Voz acelerada x{factor:.2f} → {editor.duracion(voz):.1f}s")
    return [(w, a / factor, b / factor) for w, a, b in palabras]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tema", default="", help="Tema en español (opcional)")
    ap.add_argument("--tema-en", default="", help="Tema en inglés (opcional)")
    ap.add_argument("--idiomas", default="", help="es,en")
    ap.add_argument("--ideas", action="store_true", help="Solo proponer ideas")
    ap.add_argument("--simulacion", action="store_true", help="Prueba sin APIs")
    ap.add_argument("--salida", default=str(RAIZ / "salida"))
    a = ap.parse_args()

    cfg = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))
    idiomas = [x.strip() for x in (a.idiomas or ",".join(cfg["idiomas"])).split(",") if x.strip()]
    historial = cargar_historial()
    hechos = [h["tema"]["es"] for h in historial]

    if a.simulacion:
        guion, rev = json.loads(json.dumps(GUION_PRUEBA)), {"puntajes": "simulación", "aprobado": True}
        mod_texto = mod_img = None
    else:
        from . import ia
        mod_texto, mod_img = ia.elegir_modelos(cfg)
        log(f"🤖 Proveedor {ia.PROVEEDOR}: texto={mod_texto}  imágenes={mod_img}")

        if a.ideas:
            from . import agentes
            resumen("## 💡 Ideas propuestas\n\nCopia la que te guste en el campo *tema* y vuelve a correr.\n")
            for i, idea in enumerate(agentes.proponer_ideas(mod_texto, 10, hechos), 1):
                log(f"{i:2d}. {idea['es']}  /  {idea['en']}  [{idea.get('categoria','')}]")
                log(f"    → {idea.get('por_que_engancha','')}")
                resumen(f"{i}. **{idea['es']}** / {idea['en']}  \n   _{idea.get('por_que_engancha','')}_")
            return

        tema_es, tema_en = a.tema, a.tema_en
        if not tema_es:
            from . import agentes
            log("💡 Buscando idea nueva…")
            idea = agentes.proponer_ideas(mod_texto, 5, hechos)[0]
            tema_es, tema_en = idea["es"], idea["en"]
        log(f"🎬 Tema: {tema_es} / {tema_en or '(se adapta)'}")
        guion = None

    tema_base = guion["tema"]["en"] if guion else (tema_en or tema_es)
    fecha = dt.datetime.now().strftime("%Y-%m-%d")
    carpeta = Path(a.salida) / f"{fecha}_{slug(tema_base)}"
    carpeta.mkdir(parents=True, exist_ok=True)

    if not a.simulacion:
        guion, rev = obtener_guion(mod_texto, tema_es, tema_en or "", cfg, carpeta)
        carpeta_final = Path(a.salida) / f"{fecha}_{slug(guion['tema']['en'])}"
        if carpeta_final != carpeta and not carpeta_final.exists():
            carpeta.rename(carpeta_final)
            carpeta = carpeta_final
    (carpeta / "guion.json").write_text(json.dumps(guion, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    if not rev.get("aprobado"):
        log("⚠️  El verificador no aprobó del todo el guion; revisa verificacion.json antes de publicar.")

    # Imágenes (compartidas por los dos idiomas)
    imagenes = []
    for i, esc in enumerate(guion["escenas"], 1):
        ruta = carpeta / f"img_{i:02d}.png"
        if not ruta.exists():
            if a.simulacion:
                _imagen_prueba(i, ruta)
            else:
                from . import ia
                log(f"🎨 Imagen {i}/{len(guion['escenas'])}…")
                ia.generar_imagen(mod_img, f"{cfg['estilo_visual']} Scene: {esc['imagen']}",
                                  ruta, ia.TAMANO_IMAGEN)
        imagenes.append(ruta)

    # Un video por idioma
    for idioma in idiomas:
        textos = [e[idioma] for e in guion["escenas"]]
        texto = " ".join(textos)
        voz = carpeta / f"voz_{idioma}.mp3"
        log(f"🎙️  Voz ({idioma})…")
        if a.simulacion:
            palabras = _voz_prueba(texto, voz)
        else:
            from . import eleven
            voz_id = eleven.resolver_voz(cfg["voces"][idioma])
            palabras = eleven.narrar(texto, voz_id, cfg["voz_modelo"], cfg["voz_ajustes"], voz, idioma)
        lo, hi = cfg["duracion_objetivo"]
        palabras = ajustar_velocidad(voz, palabras, hi)
        segundos = editor.duracion(voz)
        aviso = "" if lo <= segundos + editor.COLA <= hi + 5 else f"  ⚠️ fuera de {lo}-{hi}s"
        log(f"   Duración de la narración: {segundos:.1f}s{aviso}")

        log(f"🎞️  Editando ({idioma})…")
        destino = carpeta / f"{idioma}.mp4"
        editor.montar(imagenes, [e.get("movimiento", "zoom_in") for e in guion["escenas"]],
                      textos, palabras, voz, guion["tema"][idioma], destino,
                      carpeta / f"trabajo_{idioma}", RAIZ / "assets" / "musica",
                      cfg["musica_volumen"], cfg["efectos_volumen"])
        meta = (f"TÍTULO:\n{guion['titulo'][idioma]}\n\nDESCRIPCIÓN:\n{guion['descripcion'][idioma]}\n\n"
                f"{' '.join(guion['hashtags'][idioma])}\n")
        (carpeta / f"publicar_{idioma}.txt").write_text(meta, encoding="utf-8")
        log(f"✅ Listo: {destino} ({editor.duracion(destino):.1f}s)")

    estado = "✅ aprobado" if rev.get("aprobado") else "⚠️ revisar antes de publicar"
    resumen(f"## 🎬 {guion['tema']['es']}\n\n**Verificador:** {estado}  \n"
            f"**Puntajes:** {rev.get('puntajes')}\n\n"
            + "".join(f"- **{i.upper()}:** {guion['titulo'][i]}\n" for i in idiomas)
            + "\nDescarga los videos en **Artifacts**, al final de esta página.")
    if not a.simulacion:
        historial.append({"fecha": fecha, "tema": guion["tema"], "carpeta": carpeta.name,
                          "puntajes": rev.get("puntajes"), "aprobado": rev.get("aprobado")})
        guardar_historial(historial)
    log(f"📁 Todo en: {carpeta}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:                       # mensaje claro en GitHub Actions
        msg = str(e).replace("\n", " ")[:900]
        print(f"\n❌ Error: {msg}", file=sys.stderr)
        print(f"::error title=Fabrica::{msg}")
        resumen(f"## ❌ Error\n\n{msg}")
        raise
