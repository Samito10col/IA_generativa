"""Mezcla la narración con el ambiente para producir la pista completa de la escena.

La voz y el ambiente también se guardan por separado, para que en la interfaz
se puedan escuchar de forma independiente (el sonido debe distinguirse de la voz).
"""
from math import gcd

import numpy as np
import soundfile as sf
from scipy import signal

import config


def _mono(x):
    return x.mean(axis=1) if x.ndim > 1 else x


def _remuestrear(x, sr_origen, sr_destino):
    if sr_origen == sr_destino:
        return x
    g = gcd(sr_origen, sr_destino)
    return signal.resample_poly(x, sr_destino // g, sr_origen // g)


def _repetir(x, n, sr):
    """Repite el ambiente hasta n muestras con fundido cruzado entre repeticiones."""
    if len(x) >= n:
        return x[:n]
    cruce = min(int(0.5 * sr), len(x) // 4)
    salida = x.copy()
    rampa = np.linspace(0, 1, cruce)
    while len(salida) < n:
        salida[-cruce:] = salida[-cruce:] * (1 - rampa) + x[:cruce] * rampa
        salida = np.concatenate([salida, x[cruce:]])
    return salida[:n]


def _rms(x):
    return float(np.sqrt(np.mean(x ** 2))) or 1e-9


def envolvente_voz(voz, sr, ataque=0.15, liberacion=0.6):
    """Curva 0..1 que vale 1 mientras la voz suena y 0 en silencios,
    con subida rápida y bajada lenta (para que el ambiente no "bombee")."""
    ventana = max(1, int(0.05 * sr))
    energia = np.convolve(np.abs(voz), np.ones(ventana) / ventana, mode="same")
    activa = (energia > 0.1 * (energia.max() or 1)).astype(np.float32)
    # Se calcula a 200 muestras por segundo (suficiente para una curva de volumen)
    paso = max(1, sr // 200)
    control = activa[::paso]
    sr_c = sr / paso
    a, l = np.exp(-1 / (ataque * sr_c)), np.exp(-1 / (liberacion * sr_c))
    env_c = np.empty_like(control)
    previo = 0.0
    for i, x in enumerate(control):
        coef = a if x > previo else l
        previo = coef * previo + (1 - coef) * x
        env_c[i] = previo
    return np.interp(np.arange(len(voz)), np.arange(len(control)) * paso, env_c).astype(np.float32)


def mezclar(ruta_voz, ruta_ambiente, ruta_salida):
    voz, sr = sf.read(str(ruta_voz), dtype="float32")
    amb, sr_amb = sf.read(str(ruta_ambiente), dtype="float32")
    voz, amb = _mono(voz), _remuestrear(_mono(amb), sr_amb, sr)

    ini, fin = int(config.SILENCIO_INICIAL * sr), int(config.SILENCIO_FINAL * sr)
    total = ini + len(voz) + fin
    pista_voz = np.zeros(total, dtype=np.float32)
    pista_voz[ini:ini + len(voz)] = voz

    # Ambiente: repetido hasta cubrir todo, al nivel de referencia de la voz
    amb = _repetir(amb, total, sr)
    amb = amb / _rms(amb) * _rms(voz[np.abs(voz) > 0.02] if np.any(np.abs(voz) > 0.02) else voz)

    # Ducking: alto en entrada, salida y pausas; bajo mientras se narra
    env = envolvente_voz(pista_voz, sr)
    ganancia = config.AMBIENTE_ALTO - (config.AMBIENTE_ALTO - config.AMBIENTE_BAJO) * env
    amb = amb * ganancia

    f_in, f_out = int(1.0 * sr), int(2.0 * sr)
    amb[:f_in] *= np.linspace(0, 1, f_in)
    amb[-f_out:] *= np.linspace(1, 0, f_out)

    mezcla = pista_voz + amb
    pico = np.max(np.abs(mezcla))
    if pico > 0.98:
        mezcla = mezcla / pico * 0.98
    sf.write(str(ruta_salida), mezcla.astype(np.float32), sr)
    return ruta_salida
