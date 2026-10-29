"""Los agentes: ideas, guionista y verificador.

Cada uno es una llamada a Gemini con su propio rol. El guionista escribe el
video en español e inglés a la vez, escena por escena, para que las mismas
imágenes sirvan para los dos canales.
"""
from . import gemini

# ---------------------------------------------------------------- ideas

IDEAS_ROL = """Eres el productor de un canal de videos cortos "¿Qué pasaría si…?" / "What if…?".
Propones escenarios hipotéticos que hacen que la gente se detenga a ver: imposibles pero
explicables con ciencia, historia, economía, el cuerpo humano, la naturaleza, el espacio o la
vida diaria. Buscas variedad de temas, curiosidad inmediata y respuestas sorprendentes.
Evitas: política partidista, tragedias reales recientes, violencia gráfica, contenido para
niños, temas médicos que parezcan consejo, y cualquier cosa que no se pueda explicar con datos."""


def proponer_ideas(modelo, cantidad=10, evitar=()):
    evitar_txt = "\n".join(f"- {t}" for t in list(evitar)[-80:]) or "(ninguno)"
    prompt = f"""Propón {cantidad} ideas nuevas y variadas.
Temas ya hechos (NO repetir ni hacer variaciones cercanas):
{evitar_txt}

Devuelve JSON:
{{"ideas": [{{"es": "¿Qué pasaría si …?", "en": "What if …?",
             "categoria": "ciencia|historia|espacio|cuerpo|dinero|naturaleza|vida diaria|tecnologia",
             "por_que_engancha": "una frase"}}]}}"""
    return gemini.generar_json(modelo, IDEAS_ROL, prompt, temperatura=1.0)["ideas"]


# ---------------------------------------------------------------- guionista

GUION_ROL = """Eres el guionista de un canal de Shorts "¿Qué pasaría si…?" en español latino neutro
y "What if…?" en inglés. Escribes guiones narrados de 62 a 75 segundos que retienen hasta el final.

Estructura obligatoria:
1. GANCHO (escena 1, máx. 3 s): la pregunta + una consecuencia impactante o inesperada.
   Nunca empieces con "Hola", "En este video" ni con la pregunta sola sin promesa.
2. ESCALADA (escenas 2 a n-2): una línea de tiempo o cadena de consecuencias que se vuelve cada vez
   más extrema ("en los primeros segundos…", "a la semana…", "en 10 años…"). Cada escena aporta un
   dato concreto y real (cifras, nombres, mecanismos). Frases cortas, ritmo rápido, sin relleno.
3. GIRO (penúltima escena): la consecuencia que nadie espera.
4. CIERRE (última escena): una pregunta directa al espectador que invite a comentar.

Reglas:
- Datos reales y verificables; cuando algo es especulación, dilo como especulación.
- La versión en inglés NO es traducción literal: es la misma escena adaptada para que suene natural
  y con la misma duración aproximada. Igual número de escenas en ambos idiomas.
- Escribe los números como se pronuncian (en español "dos mil millones", no "2.000.000.000").
- Cada escena dura entre 4 y 8 segundos narrada (unas 12 a 22 palabras).
- Por escena, un prompt de imagen en inglés que describa UNA escena visual concreta y llamativa
  (sin texto en la imagen), coherente con lo que se narra en ese momento.
- Tono: asombro y emoción contenida, como un buen documental, nunca sensacionalismo falso."""


def escribir_guion(modelo, tema_es, tema_en, cfg, notas=None, anterior=None):
    n0, n1 = cfg["escenas"]
    prompt = f"""Tema: {tema_es}  /  {tema_en}
Número de escenas: entre {n0} y {n1}.
Total narrado: 165 a 195 palabras en español y 155 a 185 en inglés.

Devuelve JSON con esta forma exacta:
{{
  "tema": {{"es": "...", "en": "..."}},
  "titulo": {{"es": "título para YouTube, máx. 70 caracteres, con gancho", "en": "..."}},
  "descripcion": {{"es": "2 frases + llamado a suscribirse", "en": "..."}},
  "hashtags": {{"es": ["#quepasariasi", "..."], "en": ["#whatif", "..."]}},
  "escenas": [
    {{"es": "texto narrado", "en": "narrated text",
      "imagen": "detailed English image prompt for this exact moment",
      "movimiento": "zoom_in|zoom_out|subir|bajar|izquierda|derecha"}}
  ],
  "datos_a_verificar": ["cada afirmación factual importante del guion, en español"]
}}"""
    if anterior and notas:
        prompt += f"""

Este es tu guion anterior:
{anterior}

El verificador pidió estos cambios. Corrígelos todos y devuelve el guion completo corregido:
{notas}"""
    return gemini.generar_json(modelo, GUION_ROL, prompt, temperatura=0.9)


# ---------------------------------------------------------------- verificador

VERIF_ROL = """Eres el editor y verificador de datos de un canal de Shorts "¿Qué pasaría si…?".
Eres exigente: tu trabajo es que el video sea verdadero, enganchador y monetizable.
Usa la búsqueda para comprobar las cifras y afirmaciones."""


def verificar(modelo, guion_json, palabras_es, palabras_en):
    prompt = f"""Revisa este guion (JSON):
{guion_json}

Conteo de palabras: español {palabras_es}, inglés {palabras_en}
(objetivo: 165-195 en español y 155-185 en inglés para durar 62-75 s).

Evalúa del 1 al 10:
- veracidad: ¿los datos son correctos? Marca cada error con la corrección.
- gancho: ¿los primeros 3 segundos detienen el scroll?
- ritmo: ¿cada escena aporta algo nuevo, sin relleno?
- final: ¿el giro sorprende y la pregunta final invita a comentar?
- ingles: ¿la versión en inglés suena natural, no traducida?
- seguridad: ¿nada que rompa normas de YouTube/TikTok (violencia gráfica, desinformación médica,
  odio, contenido sexual)?

Devuelve SOLO JSON:
{{"puntajes": {{"veracidad": 0, "gancho": 0, "ritmo": 0, "final": 0, "ingles": 0, "seguridad": 0}},
  "aprobado": true/false,
  "cambios": ["cambio concreto 1", "..."]}}
Aprueba solo si todos los puntajes son 7 o más, veracidad y seguridad 8 o más,
y el conteo de palabras está en el rango."""
    return gemini.generar_json(modelo, VERIF_ROL, prompt, buscar=True, temperatura=0.2)
