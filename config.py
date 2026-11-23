"""Configuración central del proyecto Storybook.

Todas las rutas, nombres de modelos y parámetros por defecto están aquí,
para que el resto del código no tenga valores "quemados".
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
SALIDAS_DIR = BASE_DIR / "salidas"

# ---------------------------------------------------------------- Texto (LLM)
# Modelo servido localmente por Ollama. Se puede cambiar con la variable de
# entorno STORYBOOK_LLM (por ejemplo: set STORYBOOK_LLM=qwen2.5:3b).
OLLAMA_MODEL = os.getenv("STORYBOOK_LLM", "qwen3:4b-instruct")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
LLM_TEMPERATURA = 0.8
LLM_CONTEXTO = 4096
LLM_INTENTOS = 3
LLM_PENALIZACION_REPETICION = 1.15  # >1 desalienta que el modelo repita frases

# Largo de cada escena (palabras). El enunciado no fija un número; con 50-80
# cada escena se lee en ~30 s y el modelo pequeño no pierde el hilo.
ESCENA_PALABRAS_MIN = 50
ESCENA_PALABRAS_MAX = 80

# ---------------------------------------------------------------- Imagen
SD_REPO = "CompVis/stable-diffusion-v1-4"
SD_DIR = MODELS_DIR / "stable-diffusion-v1-4"

# Modelos de imagen disponibles (todos de la familia Stable Diffusion 1.x, misma arquitectura)
MODELOS_IMAGEN = {
    # SD 1.5 afinado para ilustración: mucha mejor calidad con los mismos recursos
    "dreamshaper8": {"repo": "Lykon/dreamshaper-8", "dir": MODELS_DIR / "dreamshaper-8",
                     "nombre": "DreamShaper 8 (SD 1.5 afinado)"},
    # Modelo base de la lista orientativa del curso
    "sd14": {"repo": SD_REPO, "dir": SD_DIR, "nombre": "Stable Diffusion v1.4 (base)"},
}
MODELO_IMAGEN = "dreamshaper8"
LCM_REPO = "latent-consistency/lcm-lora-sdv1-5"
LCM_DIR = MODELS_DIR / "lcm-lora-sdv1-5"
LCM_ARCHIVO = "pytorch_lora_weights.safetensors"
IMG_TAMANO = 512

# Parámetros de cada modo de generación de imagen
MODOS_IMAGEN = {
    # SD 1.4 "normal": más lento, mejor detalle
    "estandar": {"pasos": 20, "guia": 7.5},
    # SD 1.4 + LCM-LoRA: pocos pasos, apto para CPU
    "lcm": {"pasos": 6, "guia": 1.5},
}

NEGATIVO_IMAGEN = (
    "blurry, deformed, disfigured, extra limbs, extra fingers, bad anatomy, "
    "text, watermark, signature, low quality, ugly, duplicate, cropped, "
    "flat colors, posterized, oversaturated"
)
CALIDAD_IMAGEN = "highly detailed, soft lighting, beautiful composition"

# ---------------------------------------------------------------- Voz
PIPER_REPO = "rhasspy/piper-voices"
PIPER_DIR = MODELS_DIR / "piper"
# Voces candidatas (se usa la primera que se logre descargar)
PIPER_VOCES = [
    "es/es_MX/claude/high/es_MX-claude-high",
    "es/es_MX/ald/medium/es_MX-ald-medium",
    "es/es_ES/davefx/medium/es_ES-davefx-medium",
]
VOZ_VELOCIDAD = 1.1          # >1 = más pausado (length_scale de Piper)
VOZ_PAUSA_ORACION = 0.35     # s de silencio entre oraciones
VOZ_PAUSA_EXPRESIVA = 0.6    # s tras «?», «!» o «…»
VOZ_RMS_OBJETIVO = 0.12      # volumen de la voz, igual en todas las escenas

# ---------------------------------------------------------------- Sonido
AUDIOLDM_REPO = "cvssp/audioldm-s-full-v2"
AUDIOLDM_DIR = MODELS_DIR / "audioldm-s-full-v2"
SONIDO_DURACION = 8.0      # segundos de ambiente generado
SONIDO_PASOS = 20          # pasos de difusión de AudioLDM
NEGATIVO_SONIDO = "speech, voice, talking, singing, music, low quality, distortion"

# ---------------------------------------------------------------- Mezcla
# El ambiente "se aparta" cuando habla la voz (ducking): suena en AMBIENTE_ALTO
# al inicio, al final y en las pausas, y baja a AMBIENTE_BAJO mientras se narra.
AMBIENTE_ALTO = 0.55       # proporción frente al volumen de la voz
AMBIENTE_BAJO = 0.16
SILENCIO_INICIAL = 2.0     # s de ambiente antes de que empiece la voz
SILENCIO_FINAL = 2.5       # s de ambiente al terminar la voz
AUDIO_VERSION = 2          # si cambia, los audios viejos se regeneran al escucharlos

# ---------------------------------------------------------------- Historia
NUM_ESCENAS = 5
GENEROS = ["Infantil", "Fantasía", "Aventura", "Misterio", "Terror", "Ciencia ficción"]

# Para la interfaz web: color de acento (pensado para el fondo azul cielo) y una idea de ejemplo
GENEROS_WEB = {
    "Infantil":        {"color": "#ffd95a", "ejemplo": "un gato curioso que construye un cohete de cartón para visitar la luna"},
    "Fantasía":        {"color": "#d9c2ff", "ejemplo": "una niña que descubre que su paraguas abre puertas a un reino de nubes"},
    "Aventura":        {"color": "#9ee8b4", "ejemplo": "dos hermanos que siguen un mapa antiguo por la selva del Amazonas"},
    "Misterio":        {"color": "#ffbe7a", "ejemplo": "una detective que investiga por qué el reloj de la plaza se detiene cada noche"},
    "Terror":          {"color": "#ff8a8a", "ejemplo": "un faro abandonado donde la luz se enciende sola a medianoche"},
    "Ciencia ficción": {"color": "#c4f57a", "ejemplo": "un robot jardinero que cuida el último bosque de una estación espacial"},
}
