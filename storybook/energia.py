"""Evita que Windows suspenda el equipo mientras se genera un cuento.

Si el portátil se duerme a mitad de la generación, se corta la conexión con
Ollama y se pierde el trabajo. Con SetThreadExecutionState se le avisa a
Windows que hay una tarea en curso; al terminar se restablece lo normal.
En otros sistemas operativos no hace nada.
"""
import platform
from contextlib import contextmanager

_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


@contextmanager
def mantener_despierto():
    activo = False
    if platform.system() == "Windows":
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
            activo = True
        except Exception:
            pass
    try:
        yield
    finally:
        if activo:
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
            except Exception:
                pass
