"""Narración con voz sintética local (Piper TTS).

Para que suene más natural, como un cuentacuentos:
  1. El texto se divide en oraciones y cada una se sintetiza por separado.
  2. Entre oraciones se deja una pausa (más larga tras «?», «!» o «…»).
  3. La pista final se limpia: filtro de graves (quita zumbidos), fundidos
     suaves para evitar chasquidos y volumen normalizado entre escenas.
"""
import io
import re
import wave

import numpy as np
import soundfile as sf
from scipy import signal

import config


def ruta_voz():
    elegida = config.PIPER_DIR / "voz_elegida.txt"
    if elegida.exists():
        ruta = config.PIPER_DIR / (elegida.read_text(encoding="utf-8").strip() + ".onnx")
        if ruta.exists():
            return ruta
    candidatas = sorted(config.PIPER_DIR.rglob("*.onnx"))
    if not candidatas:
        raise FileNotFoundError(
            f"No hay voces de Piper en {config.PIPER_DIR}. Ejecute: python descargar_modelos.py")
    return candidatas[0]


def dividir_oraciones(texto):
    partes = re.split(r"(?<=[.!?…])\s+", " ".join(texto.split()))
    return [p for p in (x.strip() for x in partes) if p]


def _pausa(oracion):
    if oracion.endswith(("?", "!", "…", "...")):
        return config.VOZ_PAUSA_EXPRESIVA
    return config.VOZ_PAUSA_ORACION


def limpiar_voz(audio, sr):
    """Quita graves por debajo de 70 Hz, suaviza bordes y normaliza el volumen."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size == 0:
        return audio
    audio = signal.sosfilt(signal.butter(2, 70, "highpass", fs=sr, output="sos"), audio).astype(np.float32)
    f = min(int(0.01 * sr), len(audio) // 2)
    if f:
        audio[:f] *= np.linspace(0, 1, f)
        audio[-f:] *= np.linspace(1, 0, f)
    voz_activa = audio[np.abs(audio) > 0.02]
    rms = float(np.sqrt(np.mean(voz_activa ** 2))) if voz_activa.size else 0.0
    if rms > 0:
        audio = audio * (config.VOZ_RMS_OBJETIVO / rms)
    pico = float(np.max(np.abs(audio)))
    if pico > 0.95:
        audio = audio / pico * 0.95
    return audio


class Narrador:
    def __init__(self):
        from piper import PiperVoice

        self.ruta = ruta_voz()
        self.voz = PiperVoice.load(str(self.ruta))
        self.ajustes = None
        try:
            from piper import SynthesisConfig
            self.ajustes = SynthesisConfig(length_scale=config.VOZ_VELOCIDAD)
        except Exception:
            pass  # versiones de Piper sin SynthesisConfig: se usa la velocidad por defecto

    @property
    def nombre(self):
        return self.ruta.stem

    def _oracion(self, texto):
        """Sintetiza una oración y la devuelve como (audio float32, sr)."""
        bufer = io.BytesIO()
        with wave.open(bufer, "wb") as wav:
            if hasattr(self.voz, "synthesize_wav"):
                if self.ajustes is not None:
                    self.voz.synthesize_wav(texto, wav, syn_config=self.ajustes)
                else:
                    self.voz.synthesize_wav(texto, wav)
            else:  # API antigua de Piper (1.2)
                self.voz.synthesize(texto, wav)
        bufer.seek(0)
        with wave.open(bufer, "rb") as wav:   # Piper entrega PCM de 16 bits
            sr, canales = wav.getframerate(), wav.getnchannels()
            audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        if canales > 1:
            audio = audio.reshape(-1, canales).mean(axis=1)
        return audio, sr

    def sintetizar(self, texto, ruta_salida):
        trozos, sr = [], None
        for oracion in dividir_oraciones(texto):
            audio, sr = self._oracion(oracion)
            trozos += [audio, np.zeros(int(_pausa(oracion) * sr), dtype=np.float32)]
        if not trozos:
            raise ValueError("No hay texto para narrar.")
        sf.write(str(ruta_salida), limpiar_voz(np.concatenate(trozos[:-1]), sr), sr)
        return ruta_salida
