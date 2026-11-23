"""Servidor web local de «Érase una IA» (interfaz principal).

Ejecutar:
    venv\\Scripts\\activate
    python app.py
Abre el navegador en http://127.0.0.1:7860. Todo se procesa en este computador.

Arquitectura de la interfaz:
  - web/            página (HTML + CSS + JavaScript, sin dependencias externas)
  - /api/...        rutas que usa la página (FastAPI)
  - /salidas/...    imágenes y audios generados
La generación corre en un hilo aparte y envía sus avances a la página en vivo
con Server-Sent Events (texto mientras se escribe, cada imagen al terminar).
"""
import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")          # no consultar internet
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import json
import queue
import re
import threading
import uuid
import webbrowser
from pathlib import Path
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from storybook.historia import ErrorHistoria
from storybook.imagenes import ESTRATEGIAS
from storybook.pipeline import (Opciones, cargar_cuento, generar_audio_escena, generar_cuento,
                                listar_cuentos)

WEB_DIR = config.BASE_DIR / "web"
PUERTO = int(os.getenv("STORYBOOK_PUERTO", "7860"))
config.SALIDAS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Érase una IA")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
app.mount("/salidas", StaticFiles(directory=config.SALIDAS_DIR), name="salidas")

_trabajos = {}                       # id → cola de eventos
_generando = threading.Lock()        # un cuento a la vez (la RAM no da para dos)
_audio = threading.Lock()


# ------------------------------------------------------------------ utilidades
def _url(ruta):
    """Ruta de archivo en salidas/ → URL servible, o None si aún no existe."""
    if not ruta or not Path(ruta).exists():
        return None
    rel = Path(ruta).resolve().relative_to(config.SALIDAS_DIR.resolve()).as_posix()
    version = int(Path(ruta).stat().st_mtime)   # evita que el navegador use una copia vieja
    return f"/salidas/{quote(rel)}?v={version}"


def _cuento_web(cuento):
    """Cuento con URLs en lugar de rutas del disco."""
    escenas = []
    for e in cuento["escenas"]:
        escenas.append({
            "numero": e["numero"], "texto": e["texto"],
            "imagen": _url(e.get("imagen")),
            "audio": {"mezcla": _url(e.get("audio_mezcla")), "voz": _url(e.get("audio_voz")),
                      "ambiente": _url(e.get("audio_ambiente"))},
        })
    return {
        "id": Path(cuento["carpeta"]).name, "titulo": cuento["titulo"], "genero": cuento.get("genero"),
        "idea": cuento.get("idea"), "personajes": cuento.get("personajes", []),
        "escenario": cuento.get("escenario", ""), "escenas": escenas,
        "metadatos": cuento.get("metadatos", {}),
    }


_RE_ESCENA = re.compile(r"^\*\*Escena (\d+)\.\*\* (.*)$", re.S)


def _texto_web(markdown):
    """El avance del texto llega como markdown; la página lo recibe estructurado."""
    titulo, escenas = "", []
    for bloque in markdown.split("\n\n"):
        bloque = bloque.strip()
        if bloque.startswith("## "):
            titulo = bloque[3:].strip()
        else:
            m = _RE_ESCENA.match(bloque)
            if m:
                escenas.append(m.group(2).replace(" ▌", "").strip())
    return {"tipo": "texto", "titulo": titulo, "escenas": escenas,
            "escribiendo": markdown.rstrip().endswith("▌")}


def _carpeta_valida(cuento_id):
    if cuento_id not in listar_cuentos():
        raise HTTPException(404, "No existe ese cuento.")
    return config.SALIDAS_DIR / cuento_id


# ------------------------------------------------------------------ rutas
@app.get("/")
def inicio():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/config")
def configuracion():
    return {
        "generos": [{"nombre": g, **config.GENEROS_WEB.get(g, {})} for g in config.GENEROS],
        "escenas": config.NUM_ESCENAS,
        "opciones": {
            "estrategia": {"valor": "B", "opciones": [{"id": k, "nombre": v} for k, v in ESTRATEGIAS.items()]},
            "modelo_imagen": {"valor": config.MODELO_IMAGEN, "opciones": [
                {"id": k, "nombre": v["nombre"]} for k, v in config.MODELOS_IMAGEN.items()]},
            "modo_imagen": {"valor": "lcm", "opciones": [
                {"id": "lcm", "nombre": "Rápido (LCM, 6 pasos)"},
                {"id": "estandar", "nombre": "Estándar (20 pasos, más lento)"}]},
            "modo_sonido": {"valor": "procedural", "opciones": [
                {"id": "procedural", "nombre": "Síntesis propia (instantáneo)"},
                {"id": "ia", "nombre": "IA · AudioLDM (más lento)"}]},
        },
        "semilla": 1234,
    }


class Pedido(BaseModel):
    idea: str
    genero: str
    estrategia: str = "B"
    modelo_imagen: str = config.MODELO_IMAGEN
    modo_imagen: str = "lcm"
    semilla: int = 1234


@app.post("/api/generar")
def generar(p: Pedido):
    idea, genero = p.idea.strip(), p.genero.strip()
    if not idea:
        raise HTTPException(400, "Escribe la idea de la historia.")
    if not genero:
        raise HTTPException(400, "Elige el tipo de historia.")
    if p.modelo_imagen not in config.MODELOS_IMAGEN or p.modo_imagen not in config.MODOS_IMAGEN \
            or p.estrategia not in ESTRATEGIAS:
        raise HTTPException(400, "Configuración no válida.")
    if _generando.locked():
        raise HTTPException(409, "Ya se está creando un cuento. Espera a que termine.")

    trabajo, cola = uuid.uuid4().hex, queue.Queue()
    _trabajos[trabajo] = cola
    opciones = Opciones(estrategia=p.estrategia, modelo_imagen=p.modelo_imagen,
                        modo_imagen=p.modo_imagen, semilla=p.semilla)

    def evento(tipo, **d):
        if tipo == "texto":
            cola.put(_texto_web(d["markdown"]))
        elif tipo == "historia":
            cola.put({"tipo": "historia", "cuento": _cuento_web(d["cuento"])})
        elif tipo == "imagen":
            cola.put({"tipo": "imagen", "indice": d["indice"], "url": _url(d["ruta"])})

    def trabajar():
        with _generando:
            try:
                cuento = generar_cuento(idea, genero, opciones,
                                        progreso=lambda f, m: cola.put({"tipo": "progreso", "f": f, "m": m}),
                                        evento=evento)
                cola.put({"tipo": "listo", "cuento": _cuento_web(cuento)})
            except (ErrorHistoria, FileNotFoundError) as e:
                cola.put({"tipo": "error", "mensaje": str(e)})
            except Exception as e:
                cola.put({"tipo": "error", "mensaje": f"{type(e).__name__}: {e}"})
            finally:
                cola.put(None)

    threading.Thread(target=trabajar, daemon=True).start()
    return {"trabajo": trabajo}


@app.get("/api/progreso/{trabajo}")
def progreso(trabajo: str):
    cola = _trabajos.get(trabajo)
    if cola is None:
        raise HTTPException(404, "Trabajo desconocido.")

    def flujo():
        while True:
            try:
                ev = cola.get(timeout=15)
            except queue.Empty:
                yield ": sigue vivo\n\n"   # evita que el navegador corte la conexión
                continue
            if ev is None:
                _trabajos.pop(trabajo, None)
                yield "event: fin\ndata: {}\n\n"
                return
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(flujo(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/cuentos")
def cuentos():
    lista = []
    for cid in listar_cuentos():
        try:
            c = cargar_cuento(config.SALIDAS_DIR / cid)
        except Exception:
            continue
        lista.append({"id": cid, "titulo": c["titulo"], "genero": c.get("genero"),
                      "fecha": c.get("metadatos", {}).get("fecha", ""),
                      "portada": _url(c["escenas"][0].get("imagen"))})
    return lista


@app.get("/api/cuentos/{cuento_id}")
def cuento(cuento_id: str):
    return _cuento_web(cargar_cuento(_carpeta_valida(cuento_id)))


class PedidoAudio(BaseModel):
    modo_sonido: str = "procedural"
    semilla: int = 1234


@app.post("/api/cuentos/{cuento_id}/audio/{indice}")
def audio(cuento_id: str, indice: int, p: PedidoAudio):
    carpeta = _carpeta_valida(cuento_id)
    if not 0 <= indice < config.NUM_ESCENAS:
        raise HTTPException(400, "Escena no válida.")
    if p.modo_sonido not in ("ia", "procedural"):
        raise HTTPException(400, "Modo de sonido no válido.")
    with _audio:
        try:
            rutas = generar_audio_escena(carpeta, indice, p.modo_sonido, p.semilla)
        except FileNotFoundError as e:
            raise HTTPException(500, f"Falta un modelo: {e}")
    return {"mezcla": _url(rutas["audio_mezcla"]), "voz": _url(rutas["audio_voz"]),
            "ambiente": _url(rutas["audio_ambiente"])}


if __name__ == "__main__":
    url = f"http://127.0.0.1:{PUERTO}"
    print(f"\n  Érase una IA → {url}\n  (Ctrl + C para cerrar)\n")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=PUERTO, log_level="warning")
