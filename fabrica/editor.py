"""Editor: arma el Short vertical con las imágenes, la voz y los subtítulos.

- Cada imagen se mueve (zoom o paneo suave) durante su escena.
- Subtítulos grandes palabra por palabra con la palabra actual resaltada.
- El tema queda fijo arriba para dar contexto a quien llega a mitad del video.
- Un "whoosh" suave en cada cambio de escena y música opcional por debajo.
"""
import random
import re
import subprocess
from pathlib import Path

W, H, FPS = 1080, 1920, 30
RAIZ = Path(__file__).resolve().parent.parent
FUENTES = RAIZ / "assets" / "fonts"
FUENTE = "Inter Black"
COLA = 0.6          # segundos después de la última palabra


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg falló:\n{' '.join(map(str, cmd))[:400]}\n{r.stderr[-2000:]}")
    return r


def duracion(ruta):
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "csv=p=0", str(ruta)])
    return float(r.stdout.strip())


# ------------------------------------------------------------- movimiento

def _movimiento(tipo, d):
    p = f"(on/{d})"
    p = f"({p}*{p}*(3-2*{p}))"                       # suavizado (ease in/out)
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if tipo == "zoom_out":
        return f"1.20-0.18*{p}", cx, cy
    if tipo == "subir":
        return "1.16", cx, f"(ih-ih/zoom)*(1-{p})"
    if tipo == "bajar":
        return "1.16", cx, f"(ih-ih/zoom)*{p}"
    if tipo == "izquierda":
        return "1.16", f"(iw-iw/zoom)*(1-{p})", cy
    if tipo == "derecha":
        return "1.16", f"(iw-iw/zoom)*{p}", cy
    return f"1.02+0.18*{p}", cx, cy                 # zoom_in (por defecto)


OPUESTO = {"zoom_in": "zoom_out", "zoom_out": "zoom_in", "subir": "bajar", "bajar": "subir",
           "izquierda": "derecha", "derecha": "izquierda"}
# Zonas para la segunda toma: (ancho/alto de recorte, posición x, posición y) relativos
ZONAS = [(0.62, 0.5, 0.30), (0.62, 0.5, 0.70), (0.62, 0.25, 0.5), (0.62, 0.75, 0.5)]
TOMA_MAX = 4.6      # si una escena dura más que esto, se parte en dos tomas


def clip_escena(imagen, segundos, tipo, destino, indice=0):
    """Una escena = una o dos tomas de la misma imagen."""
    if segundos <= TOMA_MAX:
        return _toma(imagen, segundos, tipo, destino)
    s1 = round(segundos * 0.55, 3)
    a = _toma(imagen, s1, tipo, destino.with_name(destino.stem + "_a.mp4"))
    f, fx, fy = ZONAS[indice % len(ZONAS)]
    recorte = (f"crop=iw*{f}:ih*{f}:(iw-iw*{f})*{fx}:(ih-ih*{f})*{fy},")
    b = _toma(imagen, segundos - s1, OPUESTO.get(tipo, "zoom_out"),
              destino.with_name(destino.stem + "_b.mp4"), recorte)
    lista = destino.with_name(destino.stem + ".txt")
    lista.write_text(f"file '{a.resolve()}'\nfile '{b.resolve()}'\n")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
          "-i", str(lista), "-c", "copy", str(destino)])
    return destino


def _toma(imagen, segundos, tipo, destino, pre=""):
    d = max(2, round(segundos * FPS))
    z, x, y = _movimiento(tipo, d)
    vf = (f"{pre}scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={d}:s={W}x{H}:fps={FPS},"
          f"setsar=1,format=yuv420p")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(imagen),
          "-vf", vf, "-frames:v", str(d), "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "18", "-r", str(FPS), str(destino)])
    return destino


# ------------------------------------------------------------- subtítulos

def _ts(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def _mostrar(palabra):
    return palabra.upper().replace("…", "").rstrip(".,;:")


def _bloques(palabras, max_palabras=3, max_chars=18):
    grupos, actual = [], []
    for item in palabras:
        if actual and len(" ".join(_mostrar(x[0]) for x in actual + [item])) > max_chars:
            grupos.append(actual)
            actual = []
        actual.append(item)
        if len(actual) >= max_palabras or re.search(r"[….,?!;:]$", item[0]):
            grupos.append(actual)
            actual = []
    if actual:
        grupos.append(actual)
    return grupos


def _ass_escape(t):
    return t.replace("\\", "").replace("{", "(").replace("}", ")")


def escribir_ass(palabras, tema, total, destino):
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{FUENTE},92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,8,4,2,70,70,520,1
Style: Tema,{FUENTE},56,&H00FFFFFF,&H00FFFFFF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,3,18,0,8,80,80,210,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = [f"Dialogue: 1,{_ts(0)},{_ts(total)},Tema,,0,0,0,,{{\\fad(250,0)}}{_ass_escape(tema.upper())}"]
    grupos = _bloques(palabras)
    for gi, g in enumerate(grupos):
        fin_g = grupos[gi + 1][0][1] if gi + 1 < len(grupos) else total
        fin_g = min(fin_g, g[-1][2] + 0.7)
        for wi, (w, s, e) in enumerate(g):
            fin = g[wi + 1][1] if wi + 1 < len(g) else fin_g
            partes = []
            for wj, (w2, _, _) in enumerate(g):
                t = _ass_escape(_mostrar(w2))
                if wj == wi:
                    partes.append(r"{\c&H0000E5FF&\fscx116\fscy116\t(0,90,\fscx106\fscy106)}" + t + r"{\r}")
                else:
                    partes.append(t)
            ev.append(f"Dialogue: 2,{_ts(s)},{_ts(fin)},Sub,,0,0,0,,{' '.join(partes)}")
    Path(destino).write_text(cab + "\n".join(ev) + "\n", encoding="utf-8")


# ------------------------------------------------------------- límites de escena

def limites_escenas(textos_escenas, palabras):
    """Momento en que empieza cada escena según la palabra donde arranca."""
    conteos = [len(t.split()) for t in textos_escenas]
    total_texto = sum(conteos)
    inicios, idx = [], 0
    for c in conteos:
        if len(palabras) == total_texto:
            pos = idx
        else:                               # por si la voz partió distinto alguna palabra
            pos = round(idx / max(1, total_texto) * len(palabras))
        pos = min(pos, len(palabras) - 1)
        inicios.append(palabras[pos][1])
        idx += c
    inicios[0] = 0.0
    return inicios


# ------------------------------------------------------------- render final

def _whoosh(destino):
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
          "anoisesrc=color=pink:duration=0.45:amplitude=0.6:sample_rate=48000",
          "-af", "highpass=f=500,lowpass=f=6000,afade=t=in:d=0.18,afade=t=out:st=0.2:d=0.25",
          str(destino)])
    return destino


def montar(imagenes, movimientos, textos_escenas, palabras, voz, tema, destino,
           trabajo, musica_dir=None, vol_musica=0.10, vol_efectos=0.18):
    trabajo = Path(trabajo)
    trabajo.mkdir(parents=True, exist_ok=True)
    total = round(duracion(voz) + COLA, 3)
    inicios = limites_escenas(textos_escenas, palabras) + [total]

    clips = []
    for i, img in enumerate(imagenes):
        seg = inicios[i + 1] - inicios[i]
        clips.append(clip_escena(img, seg, movimientos[i], trabajo / f"clip_{i+1:02d}.mp4", i))
    lista = trabajo / "clips.txt"
    lista.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    mudo = trabajo / "mudo.mp4"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
          "-i", str(lista), "-c", "copy", str(mudo)])

    ass = trabajo / "subs.ass"
    escribir_ass(palabras, tema, total, ass)
    whoosh = _whoosh(trabajo / "whoosh.wav")

    cortes = [t for t in inicios[1:-1]]
    entradas = ["-i", str(mudo), "-i", str(voz), "-i", str(whoosh)]
    filtro = (f"[0:v]subtitles='{ass}':fontsdir='{FUENTES}'[v];"
              f"[1:a]aresample=48000,apad,atrim=0:{total}[voz];")
    mezcla = ["[voz]"]
    if cortes:
        filtro += f"[2:a]asplit={len(cortes)}" + "".join(f"[w{k}]" for k in range(len(cortes))) + ";"
        for k, t in enumerate(cortes):
            ms = max(0, int((t - 0.15) * 1000))
            filtro += f"[w{k}]adelay={ms}:all=1,volume={vol_efectos}[wd{k}];"
            mezcla.append(f"[wd{k}]")
    canciones = sorted(Path(musica_dir).glob("*.mp3")) if musica_dir else []
    if canciones:
        entradas += ["-stream_loop", "-1", "-i", str(random.choice(canciones))]
        filtro += f"[3:a]aresample=48000,volume={vol_musica},afade=t=out:st={total-1.5}:d=1.5[mus];"
        mezcla.append("[mus]")
    filtro += (f"{''.join(mezcla)}amix=inputs={len(mezcla)}:normalize=0:duration=first,"
               f"loudnorm=I=-14:TP=-1.5:LRA=11,atrim=0:{total},aformat=channel_layouts=stereo[a]")
    _run(["ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", filtro,
          "-map", "[v]", "-map", "[a]", "-t", str(total),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(destino)])
    return destino
