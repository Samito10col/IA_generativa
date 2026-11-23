"""Prueba cada componente por separado, para detectar fallas de instalación.

Uso (con el venv activado):
    python probar_componentes.py texto
    python probar_componentes.py imagen
    python probar_componentes.py voz
    python probar_componentes.py sonido
    python probar_componentes.py todo
Los resultados quedan en la carpeta pruebas/.
"""
import json
import sys
import time
from pathlib import Path

import config

SALIDA = Path(__file__).resolve().parent / "pruebas"


def probar_texto():
    from storybook.historia import generar_historia
    t = time.perf_counter()
    fallos = []
    h = generar_historia(
        "un gato curioso que construye un cohete para visitar la luna", "Infantil", registro=fallos,
        al_avanzar=lambda md, s: print(f"\r  escribiendo... {md.count('**Escena ')} escenas, {s:.0f} s   ", end="", flush=True))
    print()
    for f in fallos:
        print("  aviso:", f)
    (SALIDA / "historia_prueba.json").write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Título: {h['titulo']}  ({time.perf_counter() - t:.0f} s, intentos: {h.get('_intentos')}, "
          f"velocidad: {h.get('_estadisticas_llm', {}).get('tokens_por_s')} tokens/s)")
    for e in h["escenas"]:
        print(f"  {e['numero']}. ({len(e['texto'].split())} palabras) {e['texto'][:70]}...  [{e['sonido_tipo']}]")


def probar_imagen():
    from storybook.imagenes import GeneradorImagenes
    t = time.perf_counter()
    g = GeneradorImagenes("lcm")
    print(f"Modelo cargado en {time.perf_counter() - t:.0f} s (dispositivo: {g.dispositivo})")
    t = time.perf_counter()
    g.generar("a small orange cat wearing a blue scarf next to a cardboard rocket, "
              "children's book watercolor illustration", 1234, SALIDA / "imagen_prueba.png")
    print(f"Imagen generada en {time.perf_counter() - t:.0f} s → pruebas/imagen_prueba.png")


def probar_voz():
    from storybook.voz import Narrador
    t = time.perf_counter()
    n = Narrador()
    n.sintetizar("Había una vez un gato curioso que soñaba con visitar la luna.", SALIDA / "voz_prueba.wav")
    print(f"Voz '{n.nombre}' en {time.perf_counter() - t:.1f} s → pruebas/voz_prueba.wav")


def probar_sonido():
    import soundfile as sf
    from storybook.sonido import GeneradorSonidoIA, sintetizar_procedural
    audio, sr = sintetizar_procedural("tormenta", 8)
    sf.write(SALIDA / "sonido_procedural.wav", audio, sr)
    print("Procedural OK → pruebas/sonido_procedural.wav")
    t = time.perf_counter()
    ia = GeneradorSonidoIA()
    audio, sr = ia.generar("heavy rain on a roof with distant thunder", config.SONIDO_DURACION)
    sf.write(SALIDA / "sonido_audioldm.wav", audio, sr)
    print(f"AudioLDM OK en {time.perf_counter() - t:.0f} s → pruebas/sonido_audioldm.wav")


PRUEBAS = {"texto": probar_texto, "imagen": probar_imagen, "voz": probar_voz, "sonido": probar_sonido}

if __name__ == "__main__":
    SALIDA.mkdir(exist_ok=True)
    elegidas = sys.argv[1:] or ["todo"]
    if "todo" in elegidas:
        elegidas = list(PRUEBAS)
    for nombre in elegidas:
        print(f"\n=== Prueba: {nombre} ===")
        try:
            PRUEBAS[nombre]()
        except KeyError:
            print("Opciones válidas:", ", ".join(PRUEBAS), "o todo")
        except Exception as e:
            print(f"FALLÓ: {type(e).__name__}: {e}")
