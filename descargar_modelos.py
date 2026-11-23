"""Descarga los modelos necesarios a la carpeta models/.

Se ejecuta UNA sola vez, con internet:
    python descargar_modelos.py

Después la aplicación funciona sin conexión.
El modelo de texto se descarga aparte con Ollama:
    ollama pull qwen3:4b-instruct
"""
import sys

from huggingface_hub import hf_hub_download, snapshot_download

import config


def _hay_pesos(carpeta, nombre_base):
    return any((carpeta).glob(f"{nombre_base}*"))


def descargar_stable_diffusion():
    print("\n[1/4] Stable Diffusion v1.4 (~3,5 GB)...")
    comunes = [
        "model_index.json",
        "scheduler/*",
        "tokenizer/*",
        "feature_extractor/*",
        "text_encoder/config.json",
        "unet/config.json",
        "vae/config.json",
    ]
    # Primero se intenta solo con .safetensors (formato seguro y sin duplicados)
    pesos_st = [
        "text_encoder/model.safetensors",
        "unet/diffusion_pytorch_model.safetensors",
        "vae/diffusion_pytorch_model.safetensors",
    ]
    snapshot_download(config.SD_REPO, local_dir=config.SD_DIR,
                      allow_patterns=comunes + pesos_st)

    faltan = [c for c, n in (("text_encoder", "model"), ("unet", "diffusion_pytorch_model"),
                              ("vae", "diffusion_pytorch_model"))
              if not _hay_pesos(config.SD_DIR / c, n)]
    if faltan:
        print("   No había .safetensors para", faltan, "→ se descargan los .bin")
        pesos_bin = [f"{c}/*.bin" for c in faltan]
        snapshot_download(config.SD_REPO, local_dir=config.SD_DIR, allow_patterns=pesos_bin)
    print("   OK →", config.SD_DIR)


def descargar_dreamshaper():
    info = config.MODELOS_IMAGEN["dreamshaper8"]
    print(f"\n[+] {info['nombre']} (~2 GB)...")
    comunes = ["model_index.json", "scheduler/*", "tokenizer/*", "feature_extractor/*",
               "text_encoder/config.json", "unet/config.json", "vae/config.json"]
    # Pesos en media precisión: ocupan la mitad y en CPU se convierten a float32 al cargar
    pesos = ["text_encoder/model.fp16.safetensors",
             "unet/diffusion_pytorch_model.fp16.safetensors",
             "vae/diffusion_pytorch_model.fp16.safetensors"]
    snapshot_download(info["repo"], local_dir=info["dir"], allow_patterns=comunes + pesos)
    if not any((info["dir"] / "unet").glob("*.safetensors")):
        print("   No había pesos fp16 → se descargan los normales")
        snapshot_download(info["repo"], local_dir=info["dir"], allow_patterns=[
            "text_encoder/model.safetensors", "unet/diffusion_pytorch_model.safetensors",
            "vae/diffusion_pytorch_model.safetensors"])
    print("   OK →", info["dir"])


def descargar_lcm():
    print("\n[2/4] LCM-LoRA para SD 1.x (~130 MB)...")
    hf_hub_download(config.LCM_REPO, config.LCM_ARCHIVO, local_dir=config.LCM_DIR)
    print("   OK →", config.LCM_DIR)


def descargar_voz():
    print("\n[3/4] Voz en español para Piper (~60-110 MB)...")
    config.PIPER_DIR.mkdir(parents=True, exist_ok=True)
    for voz in config.PIPER_VOCES:
        try:
            for ext in (".onnx", ".onnx.json"):
                hf_hub_download(config.PIPER_REPO, voz + ext, local_dir=config.PIPER_DIR)
            # También se descarga la tarjeta del modelo (licencia y origen de la voz)
            try:
                carpeta = voz.rsplit("/", 1)[0]
                hf_hub_download(config.PIPER_REPO, carpeta + "/MODEL_CARD", local_dir=config.PIPER_DIR)
            except Exception:
                pass
            (config.PIPER_DIR / "voz_elegida.txt").write_text(voz, encoding="utf-8")
            print("   OK →", voz)
            return
        except Exception as e:
            print(f"   No se pudo descargar {voz}: {e}")
    raise RuntimeError("No se pudo descargar ninguna voz de Piper.")


def descargar_audioldm():
    print("\n[4/4] AudioLDM small (~1,2 GB)...")
    snapshot_download(
        config.AUDIOLDM_REPO,
        local_dir=config.AUDIOLDM_DIR,
        ignore_patterns=["*.ckpt", "*.msgpack", "*.h5", "*.onnx", "*.md"],
    )
    print("   OK →", config.AUDIOLDM_DIR)


TODOS = {
    "sd14": descargar_stable_diffusion,
    "dreamshaper": descargar_dreamshaper,
    "lcm": descargar_lcm,
    "voz": descargar_voz,
    "audioldm": descargar_audioldm,
}

if __name__ == "__main__":
    # Sin argumentos descarga todo; con argumentos solo lo indicado, p. ej.:
    #   python descargar_modelos.py dreamshaper
    elegidos = sys.argv[1:] or list(TODOS)
    pasos = [TODOS[e] for e in elegidos if e in TODOS]
    errores = []
    for paso in pasos:
        try:
            paso()
        except Exception as e:
            errores.append((paso.__name__, e))
            print(f"   ERROR en {paso.__name__}: {e}")
            if "401" in str(e) or "gated" in str(e).lower():
                print("   → El modelo pide aceptar la licencia en huggingface.co.\n"
                      "     Entre a la página del modelo, acepte las condiciones y luego\n"
                      "     ejecute 'hf auth login' con su token antes de reintentar.")

    if errores:
        print("\nTerminó con errores en:", ", ".join(n for n, _ in errores))
        print("Puede volver a ejecutar el script: lo ya descargado no se repite.")
        sys.exit(1)
    print("\nTodos los modelos quedaron en", config.MODELS_DIR)
    print("No olvide también: ollama pull", config.OLLAMA_MODEL)
