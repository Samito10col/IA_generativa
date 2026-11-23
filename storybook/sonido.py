"""Ambientación sonora de cada escena.

Dos fuentes, ambas locales:
  1. "ia":         AudioLDM (difusión texto→audio) a partir de `sonido_en`.
  2. "procedural": síntesis propia con NumPy/SciPy según `sonido_tipo`
                   (lluvia, viento, fuego, grillos, truenos, drones...).
                   No usa archivos externos, así que no hay problemas de licencia.

Si AudioLDM falla o no está instalado, se usa automáticamente el procedural.
"""
import gc

import numpy as np
import soundfile as sf
from scipy import signal

import config

SR_PROC = 22050


# ============================================================ utilidades DSP
def _ruido_blanco(n, rng):
    return rng.standard_normal(n)


def _ruido_rosa(n, rng):
    espectro = np.fft.rfft(rng.standard_normal(n))
    f = np.arange(len(espectro))
    f[0] = 1
    return _norm(np.fft.irfft(espectro / np.sqrt(f), n))


def _ruido_cafe(n, rng):
    x = np.cumsum(rng.standard_normal(n))
    x = signal.sosfilt(signal.butter(1, 20, "highpass", fs=SR_PROC, output="sos"), x)
    return _norm(x)


def _filtro(x, tipo, corte, orden=4):
    sos = signal.butter(orden, corte, tipo, fs=SR_PROC, output="sos")
    return signal.sosfilt(sos, x)


def _norm(x, pico=1.0):
    m = np.max(np.abs(x)) or 1.0
    return x / m * pico


def _lfo(n, frec, minimo=0.3, rng=None, fase=None):
    t = np.arange(n) / SR_PROC
    fase = (rng.uniform(0, 2 * np.pi) if rng is not None else 0) if fase is None else fase
    return minimo + (1 - minimo) * (0.5 + 0.5 * np.sin(2 * np.pi * frec * t + fase))


def _envolvente(n, ataque, caida):
    a = int(ataque * SR_PROC)
    env = np.exp(-np.arange(n) / (caida * SR_PROC))
    if a > 0:
        env[:a] *= np.linspace(0, 1, a)
    return env


def _insertar(base, evento, pos):
    fin = min(len(base), pos + len(evento))
    if pos < len(base):
        base[pos:fin] += evento[: fin - pos]


# ============================================================ capas de sonido
def _lluvia(n, rng):
    x = _filtro(_ruido_rosa(n, rng), "highpass", 800) * 0.5
    gotas = np.zeros(n)
    for pos in rng.integers(0, n, size=int(n / SR_PROC * 120)):
        largo = int(0.01 * SR_PROC)
        gota = rng.standard_normal(largo) * _envolvente(largo, 0, 0.002)
        _insertar(gotas, gota * rng.uniform(0.2, 1.0), pos)
    return _norm(x + _filtro(gotas, "highpass", 2000) * 0.6)


def _trueno(n, rng):
    x = np.zeros(n)
    for _ in range(rng.integers(1, 3)):
        largo = int(rng.uniform(2.0, 3.5) * SR_PROC)
        t = _filtro(_ruido_cafe(largo, rng), "lowpass", 180) * _envolvente(largo, 0.05, 0.9)
        _insertar(x, t, int(rng.uniform(0.5, max(0.6, n / SR_PROC - 3)) * SR_PROC))
    return _norm(x)


def _viento(n, rng):
    base = _ruido_rosa(n, rng)
    x = _filtro(base, "bandpass", [200, 1200]) * _lfo(n, 0.15, 0.2, rng)
    silbido = _filtro(base, "bandpass", [900, 1400], orden=2) * _lfo(n, 0.07, 0.0, rng) * 0.4
    return _norm(x + silbido)


def _agua(n, rng):
    x = _filtro(_ruido_cafe(n, rng), "lowpass", 900) * _lfo(n, 0.12, 0.3, rng)
    burbujas = np.zeros(n)
    for pos in rng.integers(0, n, size=int(n / SR_PROC * 6)):
        largo = int(0.06 * SR_PROC)
        t = np.arange(largo) / SR_PROC
        f0 = rng.uniform(400, 900)
        b = np.sin(2 * np.pi * (f0 + 3000 * t) * t) * _envolvente(largo, 0.005, 0.02)
        _insertar(burbujas, b * 0.3, pos)
    return _norm(x + burbujas)


def _fuego(n, rng):
    x = _filtro(_ruido_cafe(n, rng), "lowpass", 400) * 0.6
    chasquidos = np.zeros(n)
    for pos in rng.integers(0, n, size=int(n / SR_PROC * 25)):
        largo = int(0.015 * SR_PROC)
        c = rng.standard_normal(largo) * _envolvente(largo, 0, 0.003)
        _insertar(chasquidos, c * rng.uniform(0.3, 1.0), pos)
    return _norm(x + _filtro(chasquidos, "highpass", 1500))


def _pajaros(n, rng):
    x = np.zeros(n)
    for pos in rng.integers(0, n, size=int(n / SR_PROC * 2.5)):
        for k in range(rng.integers(2, 5)):
            largo = int(rng.uniform(0.06, 0.15) * SR_PROC)
            t = np.arange(largo) / SR_PROC
            f0, f1 = rng.uniform(2500, 4000), rng.uniform(3000, 5500)
            canto = np.sin(2 * np.pi * (f0 + (f1 - f0) * t / t[-1] / 2) * t)
            _insertar(x, canto * np.hanning(largo) * 0.5, pos + k * int(0.18 * SR_PROC))
    return _norm(x)


def _grillos(n, rng):
    x = np.zeros(n)
    for _ in range(3):
        f = rng.uniform(4200, 5200)
        periodo = rng.uniform(0.6, 1.0)
        pos = int(rng.uniform(0, periodo) * SR_PROC)
        while pos < n:
            for k in range(3):
                largo = int(0.03 * SR_PROC)
                t = np.arange(largo) / SR_PROC
                _insertar(x, np.sin(2 * np.pi * f * t) * np.hanning(largo) * 0.3,
                          pos + k * int(0.045 * SR_PROC))
            pos += int(periodo * SR_PROC)
    return _norm(x)


def _dron(n, rng, frecs, brillo=0.0):
    t = np.arange(n) / SR_PROC
    x = np.zeros(n)
    for f in frecs:
        for d in (-0.6, 0.6):  # desafinado leve para dar "movimiento"
            x += np.sin(2 * np.pi * (f + d) * t + rng.uniform(0, 2 * np.pi))
    x *= _lfo(n, 0.05, 0.6, rng)
    if brillo:
        destellos = np.zeros(n)
        for pos in rng.integers(0, n, size=int(n / SR_PROC * 3)):
            largo = int(0.8 * SR_PROC)
            tt = np.arange(largo) / SR_PROC
            nota = rng.choice([1046.5, 1318.5, 1568.0, 2093.0])
            _insertar(destellos, np.sin(2 * np.pi * nota * tt) * _envolvente(largo, 0.01, 0.3), pos)
        x = _norm(x) + destellos * brillo
    return _norm(x)


def _latido(n, rng):
    x = np.zeros(n)
    pos = int(0.3 * SR_PROC)
    while pos < n:
        for desfase, amp in ((0, 1.0), (0.22, 0.7)):
            largo = int(0.12 * SR_PROC)
            t = np.arange(largo) / SR_PROC
            golpe = np.sin(2 * np.pi * 55 * t) * _envolvente(largo, 0.005, 0.04)
            _insertar(x, golpe * amp, pos + int(desfase * SR_PROC))
        pos += int(rng.uniform(0.9, 1.1) * SR_PROC)
    return _norm(x)


def _ciudad(n, rng):
    x = _filtro(_ruido_cafe(n, rng), "lowpass", 300) * 0.7
    x += _filtro(_ruido_rosa(n, rng), "bandpass", [500, 2500]) * 0.15 * _lfo(n, 0.3, 0.3, rng)
    return _norm(x)


def _multitud(n, rng):
    base = _ruido_rosa(n, rng)
    x = _filtro(base, "bandpass", [250, 3000]) * _lfo(n, 2.5, 0.5, rng) * _lfo(n, 0.2, 0.6, rng)
    return _norm(x)


RECETAS = {
    "lluvia": [(_lluvia, 1.0)],
    "tormenta": [(_lluvia, 0.8), (_trueno, 1.0), (_viento, 0.3)],
    "viento": [(_viento, 1.0)],
    "bosque": [(_viento, 0.3), (_pajaros, 0.7)],
    "agua": [(_agua, 1.0), (_pajaros, 0.15)],
    "fuego": [(_fuego, 1.0)],
    "noche": [(_grillos, 0.8), (_viento, 0.2)],
    "ciudad": [(_ciudad, 1.0)],
    "espacio": [(lambda n, r: _dron(n, r, [55, 82.4, 110]), 1.0)],
    "magia": [(lambda n, r: _dron(n, r, [220, 277.2, 329.6], brillo=0.6), 1.0)],
    "misterio": [(lambda n, r: _dron(n, r, [73.4, 77.8, 110]), 0.8), (_viento, 0.25)],
    "terror": [(lambda n, r: _dron(n, r, [41.2, 43.6, 61.7]), 0.7), (_latido, 0.8), (_viento, 0.2)],
    "multitud": [(_multitud, 1.0)],
    "ambiente": [(_viento, 0.3), (lambda n, r: _dron(n, r, [110, 165]), 0.3)],
}


def sintetizar_procedural(tipo, duracion, semilla=0):
    """Devuelve (audio, sr) generado por código según la categoría de sonido."""
    rng = np.random.default_rng(semilla)
    n = int(duracion * SR_PROC)
    mezcla = np.zeros(n)
    for capa, volumen in RECETAS.get(tipo, RECETAS["ambiente"]):
        mezcla += capa(n, rng) * volumen
    # Entrada y salida suaves para que el bucle no "pique"
    f = int(0.5 * SR_PROC)
    mezcla[:f] *= np.linspace(0, 1, f)
    mezcla[-f:] *= np.linspace(1, 0, f)
    return _norm(mezcla, 0.8).astype(np.float32), SR_PROC


# ============================================================ fuente IA
class GeneradorSonidoIA:
    """AudioLDM (cvssp/audioldm-s-full-v2) ejecutado localmente con diffusers."""

    def __init__(self):
        import torch
        from diffusers import AudioLDMPipeline

        if not (config.AUDIOLDM_DIR / "model_index.json").exists():
            raise FileNotFoundError(f"No se encontró AudioLDM en {config.AUDIOLDM_DIR}.")
        self.torch = torch
        self.dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
        tipo = torch.float16 if self.dispositivo == "cuda" else torch.float32
        pipe = AudioLDMPipeline.from_pretrained(str(config.AUDIOLDM_DIR), torch_dtype=tipo)
        pipe.set_progress_bar_config(disable=True)
        self.pipe = pipe.to(self.dispositivo)

    def generar(self, prompt, duracion, semilla=0):
        g = self.torch.Generator(device="cpu").manual_seed(int(semilla))
        audio = self.pipe(
            prompt,
            negative_prompt=config.NEGATIVO_SONIDO,
            num_inference_steps=config.SONIDO_PASOS,
            audio_length_in_s=duracion,
            guidance_scale=2.5,
            generator=g,
        ).audios[0]
        return np.asarray(audio, dtype=np.float32), 16000

    def liberar(self):
        del self.pipe
        gc.collect()


class Ambientador:
    """Elige la fuente de sonido y hace el respaldo automático."""

    def __init__(self, modo="ia", avisos=None):
        self.modo = modo
        self.avisos = avisos if avisos is not None else []
        self.ia = None
        if modo == "ia":
            try:
                self.ia = GeneradorSonidoIA()
            except Exception as e:
                self.avisos.append(f"AudioLDM no disponible, se usa sonido procedural: {e}")
                self.modo = "procedural"

    def generar(self, escena, ruta_salida, semilla=0):
        """Genera el ambiente de la escena. Devuelve la fuente realmente usada."""
        fuente = "procedural"
        if self.ia is not None:
            try:
                audio, sr = self.ia.generar(escena["sonido_en"], config.SONIDO_DURACION, semilla)
                fuente = "audioldm"
            except Exception as e:
                self.avisos.append(f"Escena {escena['numero']}: AudioLDM falló ({e}); se usa procedural.")
                audio, sr = sintetizar_procedural(escena["sonido_tipo"], config.SONIDO_DURACION, semilla)
        else:
            audio, sr = sintetizar_procedural(escena["sonido_tipo"], config.SONIDO_DURACION, semilla)
        sf.write(str(ruta_salida), audio, sr)
        return fuente

    def liberar(self):
        if self.ia is not None:
            self.ia.liberar()
            self.ia = None
