"""Interfaz alternativa en Gradio ("modo laboratorio") para experimentos.

La interfaz principal es la página web de app.py. Esta se conserva porque
muestra todos los parámetros y es cómoda para comparar configuraciones.

Ejecutar:
    venv\\Scripts\\activate
    python app_gradio.py
Se abre en el navegador (http://127.0.0.1:7861).

Orden: primero se escribe el texto (se ve en vivo), luego se generan las
ilustraciones (aparecen una por una) y el audio de cada escena se genera al
presionar "Escuchar". La generación corre en un hilo aparte y avisa cada
avance por una cola.
"""
import os

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
os.environ.setdefault("HF_HUB_OFFLINE", "1")          # no consultar internet
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import copy
import queue
import threading
from pathlib import Path

import gradio as gr

import config
from storybook.historia import ErrorHistoria
from storybook.imagenes import ESTRATEGIAS
from storybook.pipeline import (Opciones, cargar_cuento, generar_audio_escena, generar_cuento,
                                listar_cuentos)

MODOS_IMAGEN = {"lcm": "Rápido · SD 1.4 + LCM-LoRA (6 pasos)",
                "estandar": "Estándar · SD 1.4 (20 pasos, más lento)"}
MODELOS_IMG = {k: v["nombre"] for k, v in config.MODELOS_IMAGEN.items()}
MODOS_SONIDO = {"ia": "IA · AudioLDM (más lento)", "procedural": "Procedural · síntesis propia (instantáneo)"}


def _clave(diccionario, etiqueta):
    return next(k for k, v in diccionario.items() if v == etiqueta)


def _si_existe(ruta):
    return ruta if ruta and Path(ruta).exists() else None


# ------------------------------------------------------------------ vistas
def mostrar_escena(cuento, i):
    """Contenido de la escena i. Lo que aún no se ha generado se muestra vacío."""
    if not cuento:
        return ("### Aún no hay cuento", None, "", None, None, None, "Escena – / –")
    n = len(cuento["escenas"])
    i = max(0, min(int(i or 0), n - 1))
    esc = cuento["escenas"][i]
    pendiente = []
    if not _si_existe(esc.get("imagen")):
        pendiente.append("ilustración")
    nota = f" · ⏳ generando {' y '.join(pendiente)}..." if pendiente else ""
    encabezado = f"## {cuento['titulo']}\n**Escena {i + 1} de {n}** · {cuento.get('genero', '')}{nota}"
    return (encabezado, _si_existe(esc.get("imagen")), esc["texto"],
            _si_existe(esc.get("audio_mezcla")), _si_existe(esc.get("audio_voz")),
            _si_existe(esc.get("audio_ambiente")), f"Escena {i + 1} / {n}")


def texto_completo(cuento):
    if not cuento:
        return ""
    partes = [f"## {cuento['titulo']}"]
    partes += [f"**Escena {e['numero']}.** {e['texto']}" for e in cuento["escenas"]]
    return "\n\n".join(partes)


def barra(fraccion, mensaje):
    pct = int(max(0.0, min(1.0, fraccion)) * 100)
    return (f"<div style='font-size:0.95rem;margin-bottom:6px'>{mensaje}</div>"
            f"<div style='background:#33333355;border-radius:8px;height:12px;overflow:hidden'>"
            f"<div style='width:{pct}%;height:100%;background:#f97316;transition:width .5s'></div></div>"
            f"<div style='text-align:right;font-size:0.8rem;opacity:.7'>{pct}%</div>")


def detalles(cuento):
    if not cuento:
        return ""
    m = cuento.get("metadatos", {})
    t = m.get("tiempos_s", {})
    o = m.get("opciones", {})
    llm = m.get("estadisticas_llm", {})
    pers = "\n".join(f"- **{p['nombre']}**: {p['descripcion']}" for p in cuento["personajes"])
    avisos = "\n".join(f"- {a}" for a in m.get("avisos", [])) or "- Ninguno"
    return (f"**Personajes**\n{pers}\n\n**Escenario:** {cuento.get('escenario', '')}\n\n"
            f"**Configuración:** texto `{o.get('modelo_texto')}` · estrategia `{o.get('estrategia')}` · "
            f"modelo imagen `{o.get('modelo_imagen')}` · "
            f"imagen `{o.get('modo_imagen')}` · sonido `{o.get('modo_sonido')}` · semilla `{o.get('semilla')}` · "
            f"voz `{m.get('voz')}`\n\n"
            f"**Tiempos (s):** texto {t.get('texto')} · imágenes {t.get('imagenes')} · voz {t.get('voz')} · "
            f"sonido {t.get('sonido')} · total **{t.get('total')}** · LLM {llm.get('tokens_por_s')} tokens/s\n\n"
            f"**Avisos**\n{avisos}\n\nCarpeta: `{cuento.get('carpeta')}`")


# ------------------------------------------------------------------ acciones
def preparar():
    """Antes de generar: bloquea el botón y vuelve a la escena 1."""
    return gr.Button(interactive=False, value="⏳ Generando..."), 0, None, barra(0, "Iniciando..."), ""


def generar(idea, genero, estrategia, modelo_img, modo_img, modo_son, semilla):
    idea, genero = (idea or "").strip(), (genero or "").strip()
    if not idea:
        raise gr.Error("Escriba la idea de la historia.")
    if not genero:
        raise gr.Error("Seleccione o escriba el tipo de historia.")
    opciones = Opciones(
        estrategia=_clave(ESTRATEGIAS, estrategia),
        modo_imagen=_clave(MODOS_IMAGEN, modo_img),
        modelo_imagen=_clave(MODELOS_IMG, modelo_img),
        modo_sonido=_clave(MODOS_SONIDO, modo_son),
        semilla=int(semilla or 0),
    )

    cola = queue.Queue()
    resultado = {}

    def trabajar():
        try:
            resultado["cuento"] = generar_cuento(
                idea, genero, opciones,
                progreso=lambda f, m: cola.put(("progreso", {"f": f, "m": m})),
                evento=lambda tipo, **d: cola.put((tipo, d)))
        except Exception as e:  # se reporta en la interfaz
            resultado["error"] = e
        finally:
            cola.put(("fin", {}))

    threading.Thread(target=trabajar, daemon=True).start()

    cuento, estado, en_vivo = None, barra(0, "Iniciando..."), ""
    while True:
        tipo, d = cola.get()
        # Si llegaron varios avisos seguidos, se procesan juntos (menos parpadeo)
        lote = [(tipo, d)]
        while not cola.empty() and lote[-1][0] != "fin":
            lote.append(cola.get())
        for tipo, d in lote:
            if tipo == "progreso":
                estado = barra(d["f"], d["m"])
            elif tipo == "texto":
                en_vivo = d["markdown"]
            elif tipo == "historia":
                cuento = d["cuento"]
                cuento["_version"] = 0
                en_vivo = texto_completo(cuento)
            elif tipo == "imagen" and cuento:
                # El archivo ya existe en disco; se cambia la versión para que la
                # interfaz note el cambio y refresque la escena que se está viendo.
                cuento["_version"] += 1
        yield copy.deepcopy(cuento), estado, en_vivo
        if lote[-1][0] == "fin":
            break

    if "error" in resultado:
        e = resultado["error"]
        mensaje = str(e) if isinstance(e, (ErrorHistoria, FileNotFoundError)) else f"{type(e).__name__}: {e}"
        yield cuento, barra(0, f"❌ {mensaje}"), en_vivo
        raise gr.Error(mensaje)

    final = resultado["cuento"]
    t = final.get("metadatos", {}).get("tiempos_s", {}).get("total")
    yield final, barra(1, f"✅ Listo en {t} s. Use «🔊 Escuchar» en cada escena."), texto_completo(final)


def escuchar(cuento, i, modo_son, semilla):
    """Genera (si hace falta) y reproduce el audio de la escena actual."""
    if not cuento or not cuento.get("carpeta"):
        raise gr.Error("Primero genere o abra un cuento.")
    i = int(i or 0)
    if not (Path(cuento["carpeta"]) / "historia.json").exists():
        raise gr.Error("Espere a que termine de escribirse el texto.")
    try:
        rutas = generar_audio_escena(cuento["carpeta"], i, _clave(MODOS_SONIDO, modo_son), int(semilla or 0))
    except FileNotFoundError as e:
        raise gr.Error(f"Falta un modelo: {e}")
    return rutas["audio_mezcla"], rutas["audio_voz"], rutas["audio_ambiente"]


def terminar():
    lista = listar_cuentos()
    return (gr.Button(interactive=True, value="✨ Generar cuento"),
            gr.Dropdown(choices=lista, value=lista[0] if lista else None))


def abrir(nombre):
    if not nombre:
        raise gr.Error("Seleccione un cuento de la lista.")
    cuento = cargar_cuento(config.SALIDAS_DIR / nombre)
    return cuento, 0, texto_completo(cuento), barra(1, f"📂 {cuento['titulo']}")


def mover(cuento, i, paso):
    if not cuento:
        return (0, *mostrar_escena(None, 0))
    i = max(0, min(int(i or 0) + paso, len(cuento["escenas"]) - 1))
    return (i, *mostrar_escena(cuento, i))


# ------------------------------------------------------------------ diseño
with gr.Blocks(title="Storybook IA local") as demo:
    cuento_st = gr.State(None)
    indice_st = gr.State(0)

    gr.Markdown("# 📖 Storybook IA\nCuentos ilustrados con narración y ambiente sonoro, generados 100 % en este computador.")

    with gr.Row():
        with gr.Column(scale=1, min_width=320):
            idea = gr.Textbox(label="Idea de la historia", lines=3,
                              placeholder="Ej.: un gato curioso que construye un cohete para visitar la luna")
            genero = gr.Dropdown(config.GENEROS, value=config.GENEROS[0], label="Tipo de historia",
                                 allow_custom_value=True)
            with gr.Accordion("Configuración avanzada (para experimentos)", open=False):
                estrategia = gr.Radio(list(ESTRATEGIAS.values()), value=ESTRATEGIAS["B"],
                                      label="Estrategia de consistencia visual")
                modelo_img = gr.Radio(list(MODELOS_IMG.values()), value=MODELOS_IMG[config.MODELO_IMAGEN],
                                      label="Modelo de imagen")
                modo_img = gr.Radio(list(MODOS_IMAGEN.values()), value=MODOS_IMAGEN["lcm"],
                                    label="Generación de imagen")
                modo_son = gr.Radio(list(MODOS_SONIDO.values()), value=MODOS_SONIDO["ia"],
                                    label="Ambientación sonora")
                semilla = gr.Number(value=1234, precision=0, label="Semilla")
            btn_generar = gr.Button("✨ Generar cuento", variant="primary")
            estado = gr.HTML(barra(0, "Listo para generar"))

            with gr.Accordion("Abrir un cuento ya generado", open=False):
                lista = listar_cuentos()
                guardados = gr.Dropdown(lista, value=lista[0] if lista else None, label="Cuentos guardados")
                btn_abrir = gr.Button("📂 Abrir")

        with gr.Column(scale=2):
            with gr.Accordion("📝 El cuento (se escribe en vivo)", open=True):
                en_vivo = gr.Markdown("")
            encabezado = gr.Markdown("### Aún no hay cuento")
            with gr.Row():
                imagen = gr.Image(label="Ilustración", type="filepath", height=420, interactive=False)
                with gr.Column():
                    texto = gr.Textbox(label="Texto de la escena", lines=10, interactive=False)
                    btn_escuchar = gr.Button("🔊 Escuchar esta escena", variant="secondary")
                    audio_mezcla = gr.Audio(label="▶ Escena completa (voz + ambiente)", type="filepath",
                                            autoplay=True, interactive=False)
            with gr.Row():
                audio_voz = gr.Audio(label="Solo narración", type="filepath", interactive=False)
                audio_amb = gr.Audio(label="Solo ambiente", type="filepath", interactive=False)
            with gr.Row():
                btn_ant = gr.Button("⬅ Anterior")
                marcador = gr.Markdown("Escena – / –")
                btn_sig = gr.Button("Siguiente ➡")
            with gr.Accordion("Detalles técnicos de este cuento", open=False):
                info = gr.Markdown()

    vista = [encabezado, imagen, texto, audio_mezcla, audio_voz, audio_amb, marcador]

    # Cada vez que el cuento cambia (llega texto, imagen o audio) se refresca la escena actual,
    # respetando la escena que el usuario esté viendo.
    cuento_st.change(mostrar_escena, [cuento_st, indice_st], vista, show_progress="hidden")

    (btn_generar.click(preparar, None, [btn_generar, indice_st, cuento_st, estado, en_vivo],
                       show_progress="hidden")
     .then(generar, [idea, genero, estrategia, modelo_img, modo_img, modo_son, semilla],
           [cuento_st, estado, en_vivo], show_progress="hidden")
     .then(terminar, None, [btn_generar, guardados], show_progress="hidden")
     .then(detalles, [cuento_st], [info], show_progress="hidden"))

    (btn_abrir.click(abrir, [guardados], [cuento_st, indice_st, en_vivo, estado])
     .then(detalles, [cuento_st], [info]))
    btn_escuchar.click(escuchar, [cuento_st, indice_st, modo_son, semilla],
                       [audio_mezcla, audio_voz, audio_amb])
    btn_ant.click(lambda c, i: mover(c, i, -1), [cuento_st, indice_st], [indice_st, *vista],
                  show_progress="hidden")
    btn_sig.click(lambda c, i: mover(c, i, +1), [cuento_st, indice_st], [indice_st, *vista],
                  show_progress="hidden")


if __name__ == "__main__":
    config.SALIDAS_DIR.mkdir(parents=True, exist_ok=True)
    demo.queue(default_concurrency_limit=4).launch(
        server_name="127.0.0.1", server_port=7861, inbrowser=True, allowed_paths=[str(config.SALIDAS_DIR)])
