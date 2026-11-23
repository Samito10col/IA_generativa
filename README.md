# 📖 Érase una IA: cuentos ilustrados generados localmente

Proyecto integrador de la Electiva de Inteligencia Artificial Generativa, Ingeniería de Sistemas, Universidad Santo Tomás, Seccional Tunja.

**Integrantes:** Samuel Nicolás Ávila Veloza
**Video de demostración:** https://www.youtube.com/watch?v=fQCtJDMy7XA 
A partir de una **idea** y un **tipo de historia**, la aplicación genera un cuento de **exactamente 5 escenas**. Cada escena tiene texto, una ilustración, narración con voz sintética y ambientación sonora. **Todo se ejecuta en el computador local**: no usa APIs de pago ni servicios remotos.

| Componente | Modelo / herramienta | Ejecución |
|---|---|---|
| Texto | Qwen3-4B-Instruct-2507 (vía Ollama) | Local |
| Imagen | DreamShaper 8 (SD 1.5 afinado) + LCM-LoRA (diffusers); SD v1.4 como alternativa | Local |
| Voz | Piper TTS (voz en español) | Local |
| Sonido | AudioLDM-s-full-v2 (diffusers) + síntesis procedural propia | Local |
| Interfaz | Página web propia (HTML/CSS/JS) servida con FastAPI | Local (navegador) |

---

## 1. Requisitos

**Mínimo probado:** Windows 11, CPU AMD Ryzen 5 7520U (4 núcleos / 8 hilos), 16 GB de RAM, sin GPU dedicada.

- Python **3.11** (otras versiones pueden fallar con algunas librerías)
- Git
- Ollama (https://ollama.com/download)
- ~15 GB libres en disco (modelos + librerías)
- Internet **solo** para la instalación inicial

Si el equipo tiene GPU NVIDIA, el programa la detecta y la usa automáticamente.

## 2. Instalación paso a paso (Windows)

```powershell
# 1. Clonar el repositorio
git clone https://github.com/USUARIO/storybook.git
cd storybook

# 2. Crear y activar el entorno virtual
py -3.11 -m venv venv
venv\Scripts\activate
#   Si PowerShell bloquea el script:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 3. Instalar PyTorch (CPU) y las demás dependencias
python -m pip install --upgrade pip
pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

# 4. Descargar los modelos
ollama pull qwen3:4b-instruct
python descargar_modelos.py
```

`descargar_modelos.py` deja los modelos en `models/`:

```
models/
├── dreamshaper-8/              (~2 GB, modelo de imagen por defecto)
├── stable-diffusion-v1-4/      (~4 GB, para comparar)
├── lcm-lora-sdv1-5/            (~130 MB)
├── piper/es/...                (~60-110 MB)
└── audioldm-s-full-v2/         (~3,4 GB)

Para descargar solo una parte: `python descargar_modelos.py dreamshaper lcm voz` (sin SD 1.4 ni AudioLDM, si no se van a usar).
```

El modelo de texto queda en la carpeta de Ollama (`C:\Users\<usuario>\.ollama\models`).

### Instalación rápida con doble clic (Windows)

Con Python 3.11, Git y Ollama ya instalados:

1. `instalar.bat` crea el entorno, instala las librerías y descarga los modelos necesarios (DreamShaper 8, LCM, voz y Qwen3-4B).
2. `iniciar.bat` abre la aplicación.

### Instalación en otro equipo sin descargar los modelos (USB)

1. En el equipo donde ya funciona: `preparar_usb.bat E:\storybook_usb` (cambie `E:` por la letra de la USB). Copia unos 6 GB.
2. En el equipo nuevo: `git clone` del repositorio y luego `instalar.bat E:\storybook_usb`.

SD 1.4 y AudioLDM no se copian (son opcionales); si se quieren: `python descargar_modelos.py sd14 audioldm`.

## 3. Verificar la instalación

```powershell
python probar_componentes.py todo
```
Prueba cada componente por separado y deja los resultados en `pruebas/`.

## 4. Ejecución

```powershell
venv\Scripts\activate
python app.py
```
Se abre el navegador en `http://127.0.0.1:7860`. Ollama debe estar abierto (ícono junto al reloj).

Interfaz alternativa para experimentos (muestra todos los parámetros): `python app_gradio.py` → `http://127.0.0.1:7861`.

## 5. Ejemplo de uso

1. En la portada, elegir el tipo de historia (por ejemplo **Infantil**).
2. Escribir la idea: *«un gato curioso que construye un cohete de cartón para visitar la luna»* (o usar el ejemplo).
3. Clic en **Crear cuento**. Primero se ve el texto escribiéndose en vivo; luego aparecen las ilustraciones una por una.
4. Pasar las páginas del libro con las flechas (también con ← → del teclado). En cada escena, **🔊 Escuchar** genera y reproduce la narración con su ambiente sonoro (también se pueden escuchar por separado).

Cada cuento queda guardado en `salidas/<fecha>_<titulo>/` y puede volver a abrirse desde la interfaz sin generarlo de nuevo.

## 6. Configuración

Los parámetros están en `config.py`. Desde la interfaz (*Configuración avanzada*) se puede elegir:

- **Estrategia de consistencia visual**
  - **A · Básica:** el prompt de la imagen es solo la descripción de la escena, con semilla aleatoria.
  - **B · Consistente:** el prompt de cada imagen repite la ficha visual del protagonista y el estilo de ilustración, y todas usan la misma semilla.
- **Modelo de imagen:** DreamShaper 8 (por defecto) o Stable Diffusion v1.4.
- **Velocidad de imagen:** LCM (6 pasos, rápido) o estándar (20 pasos).
- **Ambiente sonoro:** síntesis propia (por defecto, instantáneo) o AudioLDM (IA, más lento).

La narración se genera oración por oración con pausas, y el ambiente baja automáticamente mientras habla la voz (*ducking*). Con **Leer todo el cuento** se narran las 5 escenas seguidas y el libro pasa las páginas solo.
- **Semilla.**

Para cambiar el modelo de texto: `set STORYBOOK_LLM=qwen2.5:3b` antes de `python app.py`.

## 7. Arquitectura y flujo de datos

```
idea + género
   │
   ▼
[Ollama · Qwen3-4B]  1) plan JSON: título, ficha de personajes, estilo, resumen de 5 escenas
                     2) escena 1..5 en texto plano (50-80 palabras, con contexto de las anteriores)
                     3) JSON: descripción visual y sonido de cada escena ──► historia.json
   │
   ├──► [Stable Diffusion 1.4 + LCM]  prompt = ficha protagonista + escena + estilo ──► escena_N.png
   │
   └──► al presionar «Escuchar» (por escena):
        [Piper TTS] texto ──► escena_N_voz.wav
        [AudioLDM / procedural] sonido_en / sonido_tipo ──► escena_N_ambiente.wav
        [Mezcla NumPy/SciPy] voz + ambiente ──► escena_N_mezcla.wav
   │
   ▼
[Página web] libro que muestra el texto en vivo (Server-Sent Events), cada ilustración al terminar,
             reproduce el audio y permite pasar las páginas
```

Cada etapa carga su modelo, procesa las 5 escenas y lo libera antes de la siguiente. Así todo cabe en 16 GB de RAM.

**Preservación de personajes y contexto:** el LLM primero fija un plan con la ficha de personajes (rasgos visuales fijos) y el resumen de las 5 escenas. Cada escena se escribe viendo ese plan y todas las escenas anteriores. La ficha y el estilo de ilustración se inyectan en el prompt de cada imagen. Escribir escena por escena, con tope de palabras y penalización de repeticiones, evita que el modelo pequeño entre en bucles (problema observado al pedir todo el cuento en una sola respuesta).

## 8. Registro de pruebas

Cada generación agrega una fila a `salidas/registro_pruebas.csv` con la idea, el género, los modelos, la estrategia, la semilla, los tiempos por etapa y los avisos. En `metadatos.json` de cada cuento quedan además el hardware y las versiones de las librerías.

## 9. Estructura del proyecto

```
storybook/
├── app.py                  Servidor web local (FastAPI) – interfaz principal
├── app_gradio.py           Interfaz alternativa (Gradio) para experimentos
├── web/                    Página: index.html, estilos.css, app.js
├── config.py               Rutas, modelos y parámetros
├── descargar_modelos.py    Descarga inicial de modelos
├── probar_componentes.py   Pruebas por componente
├── instalar.bat            Instalación con doble clic (Windows)
├── iniciar.bat             Abre la aplicación
├── preparar_usb.bat        Copia los modelos a una USB
├── requirements.txt
├── storybook/
│   ├── historia.py         LLM → historia estructurada (JSON)
│   ├── imagenes.py         Stable Diffusion + estrategias de consistencia
│   ├── voz.py              Piper TTS
│   ├── sonido.py           AudioLDM + síntesis procedural
│   ├── mezcla.py           Mezcla voz + ambiente
│   └── pipeline.py         Orquestación, guardado y registro
├── models/                 (no se sube al repositorio)
└── salidas/                (no se sube al repositorio)
```

## 10. Modelos y licencias

| Modelo | Licencia | Fuente |
|---|---|---|
| Qwen3-4B-Instruct-2507 | Apache 2.0 | huggingface.co/Qwen · ollama.com/library/qwen3 |
| DreamShaper 8 | CreativeML OpenRAIL-M | huggingface.co/Lykon/dreamshaper-8 |
| Stable Diffusion v1.4 | CreativeML OpenRAIL-M | huggingface.co/CompVis/stable-diffusion-v1-4 |
| LCM-LoRA SD1.5 | OpenRAIL++ | huggingface.co/latent-consistency/lcm-lora-sdv1-5 |
| Motor Piper (piper-tts 1.8) | GPL-3.0 (dependencia instalada con pip, no se incluye) | github.com/OHF-Voice/piper1-gpl |
| Voz es_MX-claude-high | Ver MODEL_CARD de la voz | huggingface.co/rhasspy/piper-voices |
| AudioLDM-s-full-v2 | CC BY-NC-SA 4.0 | huggingface.co/cvssp/audioldm-s-full-v2 |

Los pesos de los modelos **no se redistribuyen** en este repositorio: se descargan desde sus fuentes oficiales. El uso es académico y no comercial. Los sonidos procedurales los genera el propio código y no dependen de archivos de terceros.

## 11. Limitaciones conocidas

- En CPU, un cuento completo tarda unos 13 a 15 minutos (texto ≈ 4 min, cada ilustración ≈ 2 min; ver `registro_pruebas.csv`).
- Stable Diffusion 1.x no tiene memoria de personaje: aun con la estrategia B, detalles como la ropa pueden variar entre escenas.
- AudioLDM en CPU es lento (≈ 1 min por ambiente) y está marcado como obsoleto en diffusers. Si falla, se usa el sonido procedural.
- Una sola voz narra todo el cuento.

## 12. Licencia del código

MIT. Ver `LICENSE`.
