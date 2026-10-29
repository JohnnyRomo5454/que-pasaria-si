# Fábrica de videos ¿Qué pasaría si…? / What if…?

Genera Shorts verticales de 62–75 s en **español e inglés** a partir de un tema:

1. **Ideas**: propone temas nuevos sin repetir los que ya hiciste (`data/historial.json`).
2. **Guionista** (OpenAI por defecto; Gemini opcional): escribe el guion en los dos idiomas, escena por escena.
3. **Verificador**: revisa los datos con Google Search, el gancho, el ritmo y las normas. Si no aprueba, el guionista corrige (hasta 2 veces).
4. **Ilustrador**: una imagen por escena con Nano Banana (las mismas para ambos idiomas).
5. **Narrador**: voz de ElevenLabs con el tiempo exacto de cada palabra.
6. **Editor**: movimiento de cámara, subtítulos palabra por palabra, tema fijo arriba, efectos y música.

Costo aproximado: menos de 1 USD por tema (dos videos).

## Configuración (una sola vez)

En GitHub: **Settings → Secrets and variables → Actions → New repository secret**

| Nombre | De dónde sale |
| --- | --- |
| `OPENAI_API_KEY` | platform.openai.com → API keys (con saldo prepagado en Billing) |
| `ELEVENLABS_API_KEY` | ElevenLabs → tu perfil → API Keys (permisos: Texto a voz + Voces leído) |
| `GEMINI_API_KEY` (opcional) | Solo si cambias `"proveedor": "gemini"` en config.json |

Las voces se eligen en `config.json` (`voces.es` y `voces.en`) por su **nombre** tal como aparece en *My Voices* de ElevenLabs, o por su ID.

## Uso

**Actions → Crear video → Run workflow**

- *crear video*: con tema o vacío para que el sistema elija.
- *solo proponer ideas*: 10 ideas en el resumen de la ejecución.
- *prueba sin gastar*: revisa que todo funcione sin usar las APIs.

Al terminar, descarga **videos** en *Artifacts* (al final de la página de la ejecución). Cada carpeta trae `es.mp4`, `en.mp4`, `publicar_es.txt` / `publicar_en.txt` (título, descripción y hashtags) y `verificacion.json`.

## Música

Pon archivos `.mp3` libres de derechos en `assets/musica/` y se usará uno al azar, bajito debajo de la voz. Sin archivos, el video sale sin música (en TikTok puedes agregar un sonido en tendencia desde la app).

## En tu computadora

```
pip install -r requirements.txt     # y tener ffmpeg instalado
set GEMINI_API_KEY=...              # en Windows
set ELEVENLABS_API_KEY=...
python -m fabrica.main --tema "¿Qué pasaría si la Luna desapareciera?"
```
