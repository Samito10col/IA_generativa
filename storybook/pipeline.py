"""Orquestación: idea + género → cuento de 5 escenas con texto, imagen, voz y sonido.

Flujo de datos (en este orden):
  1. TEXTO   LLM (Ollama): plan → 5 escenas una por una → descripciones visuales y de sonido
  2. IMAGEN  Stable Diffusion: una ilustración por escena (ficha visual + escena + estilo)
  3. AUDIO   al presionar "Escuchar" en la interfaz, para cada escena:
             Piper (voz) + AudioLDM o síntesis procedural (ambiente) + mezcla
Cada etapa carga su modelo, lo usa y lo libera, para que todo quepa en 16 GB de RAM.

Cada ejecución queda guardada en salidas/<fecha>_<titulo>/ con sus metadatos,
y se agrega una fila a salidas/registro_pruebas.csv (evidencia para el informe).
"""
import csv
import json
import platform
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from importlib import metadata
from pathlib import Path

import config
from storybook.historia import generar_historia
from storybook.imagenes import construir_prompt, semilla_escena


@dataclass
class Opciones:
    estrategia: str = "B"          # "A" básica | "B" consistente
    modo_imagen: str = "lcm"       # "lcm" | "estandar"
    modelo_imagen: str = config.MODELO_IMAGEN  # "dreamshaper8" | "sd14"
    modo_sonido: str = "ia"        # "ia" (AudioLDM) | "procedural"
    semilla: int = 1234
    modelo_texto: str = config.OLLAMA_MODEL


def _slug(texto, largo=40):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:largo] or "cuento"


def _versiones():
    paquetes = ["torch", "diffusers", "transformers", "piper-tts", "gradio", "ollama"]
    v = {}
    for p in paquetes:
        try:
            v[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            v[p] = "no instalado"
    return v


def _hardware():
    info = {"sistema": f"{platform.system()} {platform.release()}",
            "procesador": platform.processor(), "python": platform.python_version()}
    try:
        import psutil
        info["ram_gb"] = round(psutil.virtual_memory().total / 1024**3, 1)
        info["nucleos_fisicos"] = psutil.cpu_count(logical=False)
        info["hilos"] = psutil.cpu_count(logical=True)
    except Exception:
        pass
    try:
        import torch
        info["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "ninguna (CPU)"
    except Exception:
        pass
    return info


def _registrar_csv(meta):
    ruta = config.SALIDAS_DIR / "registro_pruebas.csv"
    nueva = not ruta.exists()
    t = meta["tiempos_s"]
    fila = {
        "fecha": meta["fecha"], "carpeta": meta["carpeta"], "idea": meta["idea"],
        "genero": meta["genero"], "titulo": meta["titulo"],
        "modelo_texto": meta["opciones"]["modelo_texto"],
        "estrategia": meta["opciones"]["estrategia"], "modelo_imagen": meta["opciones"].get("modelo_imagen"),
        "modo_imagen": meta["opciones"]["modo_imagen"],
        "semilla": meta["opciones"]["semilla"],
        "intentos_texto": meta.get("intentos_texto"),
        "palabras_por_escena": "|".join(map(str, meta.get("palabras_por_escena", []))),
        "t_texto": t.get("texto"), "t_imagenes": t.get("imagenes"), "t_total": t.get("total"),
        "tokens_por_s": meta.get("estadisticas_llm", {}).get("tokens_por_s"),
        "avisos": " || ".join(meta.get("avisos", [])),
    }
    with open(ruta, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(fila.keys()), delimiter=";")
        if nueva:
            w.writeheader()
        w.writerow(fila)


def _rutas_absolutas(historia, carpeta):
    """Copia de la historia con rutas absolutas (para la interfaz)."""
    vista = json.loads(json.dumps(historia, ensure_ascii=False))
    for esc in vista["escenas"]:
        for clave in ("imagen", "audio_voz", "audio_ambiente", "audio_mezcla"):
            if esc.get(clave):
                esc[clave] = str(Path(carpeta) / esc[clave])
    vista["carpeta"] = str(carpeta)
    return vista


def generar_cuento(idea, genero, opciones=None, progreso=None, evento=None):
    """Genera el texto y las imágenes del cuento (el audio se genera aparte, bajo demanda).

    progreso(fraccion, mensaje): avance general (opcional).
    evento(tipo, **datos): avisos para mostrar resultados apenas existen (opcional):
        "texto"     markdown=<cuento a medio escribir>, segundos=<float>
        "historia"  cuento=<dict con rutas absolutas; imágenes aún no creadas>
        "imagen"    indice=<int>, ruta=<str>
    Devuelve el cuento (igual que cargar_cuento).
    """
    from storybook.energia import mantener_despierto

    with mantener_despierto():
        return _generar(idea, genero, opciones or Opciones(),
                        progreso or (lambda f, m: print(f"[{f:4.0%}] {m}")),
                        evento or (lambda tipo, **d: None))


def _generar(idea, genero, opciones, avisar, evento):
    from storybook.imagenes import GeneradorImagenes

    avisos, tiempos = [], {}
    t0 = time.perf_counter()
    n = config.NUM_ESCENAS

    # ---------------------------------------------------------------- 1. Texto
    avisar(0.02, f"Escribiendo la historia con {opciones.modelo_texto}...")
    t = time.perf_counter()

    def al_avanzar(markdown, segundos):
        escenas = markdown.count("**Escena ")
        avisar(min(0.03 + 0.09 * escenas, 0.48), f"Escribiendo la historia... ({segundos:.0f} s)")
        evento("texto", markdown=markdown, segundos=segundos)

    historia = generar_historia(idea, genero, modelo=opciones.modelo_texto, registro=avisos,
                                al_avanzar=al_avanzar)
    tiempos["texto"] = round(time.perf_counter() - t, 1)

    fecha = datetime.now()
    carpeta = config.SALIDAS_DIR / f"{fecha:%Y%m%d_%H%M%S}_{_slug(historia['titulo'])}"
    carpeta.mkdir(parents=True, exist_ok=True)
    historia["idea"], historia["genero"] = idea, genero
    for i, esc in enumerate(historia["escenas"], start=1):
        esc["prompt_imagen"] = construir_prompt(historia, esc, opciones.estrategia)
        esc["semilla_imagen"] = semilla_escena(opciones.estrategia, opciones.semilla, i - 1)
        esc["imagen"] = f"escena_{i}.png"
        esc["audio_voz"] = f"escena_{i}_voz.wav"
        esc["audio_ambiente"] = f"escena_{i}_ambiente.wav"
        esc["audio_mezcla"] = f"escena_{i}_mezcla.wav"
    _guardar_json(carpeta / "historia.json", historia, quitar_privados=True)
    evento("historia", cuento=_rutas_absolutas(historia, carpeta))

    # ---------------------------------------------------------------- 2. Imágenes
    t = time.perf_counter()
    avisar(0.50, f"Cargando {config.MODELOS_IMAGEN[opciones.modelo_imagen]['nombre']}...")
    gen_img = GeneradorImagenes(opciones.modo_imagen, opciones.modelo_imagen)
    for i, esc in enumerate(historia["escenas"]):
        avisar(0.52 + 0.095 * i, f"Ilustrando escena {i + 1} de {n}...")
        gen_img.generar(esc["prompt_imagen"], esc["semilla_imagen"], carpeta / esc["imagen"])
        evento("imagen", indice=i, ruta=str(carpeta / esc["imagen"]))
    gen_img.liberar()
    tiempos["imagenes"] = round(time.perf_counter() - t, 1)
    tiempos["total"] = round(time.perf_counter() - t0, 1)

    # ---------------------------------------------------------------- Guardado
    meta = {
        "fecha": fecha.isoformat(timespec="seconds"), "carpeta": carpeta.name,
        "idea": idea, "genero": genero, "titulo": historia["titulo"],
        "opciones": asdict(opciones),
        "palabras_por_escena": [len(e["texto"].split()) for e in historia["escenas"]],
        "intentos_texto": historia.pop("_intentos", None),
        "estadisticas_llm": historia.pop("_estadisticas_llm", {}),
        "tiempos_s": tiempos, "audio": {}, "avisos": avisos,
        "hardware": _hardware(), "versiones": _versiones(),
    }
    _guardar_json(carpeta / "historia.json", historia)
    _guardar_json(carpeta / "metadatos.json", meta)
    _registrar_csv(meta)
    avisar(1.0, f"Texto e imágenes listos en {tiempos['total']} s")
    return cargar_cuento(carpeta)


def _guardar_json(ruta, datos, quitar_privados=False):
    if quitar_privados:
        datos = {k: v for k, v in datos.items() if not k.startswith("_")}
    Path(ruta).write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ audio bajo demanda
_narrador = None
_ambientador = None


def _modelos_audio(modo_sonido):
    """Carga la voz y el generador de ambiente una sola vez y los reutiliza."""
    global _narrador, _ambientador
    from storybook.sonido import Ambientador
    from storybook.voz import Narrador

    if _narrador is None:
        _narrador = Narrador()
    if _ambientador is None or _ambientador.modo_pedido != modo_sonido:
        if _ambientador is not None:
            _ambientador.liberar()
        _ambientador = Ambientador(modo_sonido)
        _ambientador.modo_pedido = modo_sonido
    return _narrador, _ambientador


def generar_audio_escena(carpeta, indice, modo_sonido="ia", semilla=1234):
    """Genera (si no existen) la voz, el ambiente y la mezcla de una escena.

    Devuelve un dict con las rutas absolutas. Si ya existían, no se regeneran.
    """
    from storybook.mezcla import mezclar

    carpeta = Path(carpeta)
    historia = json.loads((carpeta / "historia.json").read_text(encoding="utf-8"))
    esc = historia["escenas"][indice]
    rutas = {k: carpeta / esc[k] for k in ("audio_voz", "audio_ambiente", "audio_mezcla")}
    ruta_meta = carpeta / "metadatos.json"
    meta = json.loads(ruta_meta.read_text(encoding="utf-8")) if ruta_meta.exists() else {}
    version = meta.get("audio", {}).get(str(indice + 1), {}).get("version", 1)
    if all(r.exists() for r in rutas.values()) and version >= config.AUDIO_VERSION:
        return {k: str(v) for k, v in rutas.items()}   # ya existe y está al día

    narrador, ambientador = _modelos_audio(modo_sonido)
    ambientador.avisos = []
    tiempos = {}
    t = time.perf_counter()
    narrador.sintetizar(esc["texto"], rutas["audio_voz"])
    tiempos["voz"] = round(time.perf_counter() - t, 1)
    t = time.perf_counter()
    fuente = ambientador.generar(esc, rutas["audio_ambiente"], semilla + indice)
    tiempos["sonido"] = round(time.perf_counter() - t, 1)
    t = time.perf_counter()
    mezclar(rutas["audio_voz"], rutas["audio_ambiente"], rutas["audio_mezcla"])
    tiempos["mezcla"] = round(time.perf_counter() - t, 1)

    # Se anota en los metadatos del cuento (evidencia para el informe)
    meta.setdefault("audio", {})[str(indice + 1)] = {
        "version": config.AUDIO_VERSION, "voz": narrador.nombre, "fuente_sonido": fuente, "tiempos_s": tiempos,
        "avisos": list(ambientador.avisos)}
    _guardar_json(ruta_meta, meta)
    return {k: str(v) for k, v in rutas.items()}


def cargar_cuento(carpeta):
    """Lee un cuento ya generado y devuelve rutas absolutas listas para la interfaz."""
    carpeta = Path(carpeta)
    historia = json.loads((carpeta / "historia.json").read_text(encoding="utf-8"))
    for esc in historia["escenas"]:
        for clave in ("imagen", "audio_voz", "audio_ambiente", "audio_mezcla"):
            esc[clave] = str(carpeta / esc[clave])
    historia["carpeta"] = str(carpeta)
    meta = carpeta / "metadatos.json"
    historia["metadatos"] = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
    return historia


def listar_cuentos():
    if not config.SALIDAS_DIR.exists():
        return []
    return sorted((p.name for p in config.SALIDAS_DIR.iterdir() if (p / "historia.json").exists()),
                  reverse=True)
