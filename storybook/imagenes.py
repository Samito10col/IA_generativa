"""Generación de ilustraciones con Stable Diffusion v1.4 (local).

Dos estrategias de consistencia visual, para compararlas en el informe:

  A ("basica"):      el prompt es solo la descripción de la escena y cada imagen
                     usa una semilla aleatoria distinta.
  B ("consistente"): el prompt repite SIEMPRE la ficha visual del protagonista y
                     el estilo de ilustración, y todas las escenas usan la misma
                     semilla.

Y dos modos de velocidad:
  "estandar": SD 1.4 con 20 pasos (DPM-Solver).
  "lcm":      SD 1.4 + LCM-LoRA con 6 pasos (mucho más rápido en CPU).
"""
import gc
import os
import random

import config

ESTRATEGIAS = {
    "B": "B · Consistente (ficha del personaje + estilo + semilla fija)",
    "A": "A · Básica (solo la escena, semilla aleatoria)",
}


def construir_prompt(historia, escena, estrategia="B"):
    escena_txt = escena["descripcion_visual_en"]
    if estrategia == "A":
        return escena_txt
    protagonista = historia["personajes"][0]["descripcion_visual_en"]
    estilo = historia["estilo_visual_en"]
    # CLIP solo lee ~77 tokens: primero el estilo y la escena (qué se ve y dónde),
    # luego los rasgos fijos del protagonista y al final los términos de calidad.
    return f"{estilo}, {escena_txt}, {protagonista}, {config.CALIDAD_IMAGEN}"


def semilla_escena(estrategia, semilla_base, indice):
    if estrategia == "A":
        return random.randint(0, 2**31 - 1)
    return int(semilla_base)


class GeneradorImagenes:
    def __init__(self, modo="lcm", modelo=None):
        import torch
        from diffusers import (DPMSolverMultistepScheduler, LCMScheduler,
                               StableDiffusionPipeline)

        if modo not in config.MODOS_IMAGEN:
            raise ValueError(f"Modo de imagen desconocido: {modo}")
        self.torch = torch
        self.modo = modo
        self.params = config.MODOS_IMAGEN[modo]
        self.dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
        if self.dispositivo == "cpu":
            # En CPU rinde más usar los núcleos físicos que todos los hilos lógicos
            try:
                import psutil
                hilos = psutil.cpu_count(logical=False) or os.cpu_count() or 4
            except Exception:
                hilos = os.cpu_count() or 4
            torch.set_num_threads(hilos)
        tipo = torch.float16 if self.dispositivo == "cuda" else torch.float32

        self.modelo = modelo or config.MODELO_IMAGEN
        info = config.MODELOS_IMAGEN[self.modelo]
        carpeta = info["dir"]
        if not (carpeta / "model_index.json").exists():
            raise FileNotFoundError(
                f"No se encontró {info['nombre']} en {carpeta}. Ejecute: python descargar_modelos.py")

        # Si solo están los pesos en media precisión (.fp16), se cargan y se pasan a float32 en CPU
        variante = "fp16" if any((carpeta / "unet").glob("*.fp16.safetensors")) and \
            not (carpeta / "unet" / "diffusion_pytorch_model.safetensors").exists() else None
        pipe = StableDiffusionPipeline.from_pretrained(
            str(carpeta),
            torch_dtype=tipo,
            variant=variante,
            safety_checker=None,
            requires_safety_checker=False,
        )

        if modo == "lcm":
            pipe.load_lora_weights(str(config.LCM_DIR), weight_name=config.LCM_ARCHIVO)
            pipe.fuse_lora()
            pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)
        else:
            pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)

        if self.dispositivo == "cuda":
            pipe.enable_attention_slicing()  # en GPU ahorra VRAM; en CPU solo la haría más lenta
        pipe.set_progress_bar_config(disable=True)
        self.pipe = pipe.to(self.dispositivo)

    def generar(self, prompt, semilla, ruta_salida):
        generador = self.torch.Generator(device="cpu").manual_seed(int(semilla))
        imagen = self.pipe(
            prompt=prompt,
            negative_prompt=config.NEGATIVO_IMAGEN,
            num_inference_steps=self.params["pasos"],
            guidance_scale=self.params["guia"],
            height=config.IMG_TAMANO,
            width=config.IMG_TAMANO,
            generator=generador,
        ).images[0]
        imagen.save(ruta_salida)
        return ruta_salida

    def liberar(self):
        del self.pipe
        gc.collect()
        if self.dispositivo == "cuda":
            self.torch.cuda.empty_cache()
