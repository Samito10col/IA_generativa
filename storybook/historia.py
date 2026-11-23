"""Generación del relato con un LLM local servido por Ollama, en tres pasos:

  1. PLAN (JSON corto): título, ficha de personajes (con rasgos visuales fijos
     en inglés), estilo de ilustración, escenario y una frase-resumen por escena.
  2. ESCENAS (texto plano, una por una): cada escena se escribe por separado,
     viendo el plan y las escenas anteriores, con un tope de palabras y
     penalización de repeticiones.
  3. ARTE Y SONIDO (JSON corto): para cada escena ya escrita, la descripción
     visual (inglés, para Stable Diffusion) y el sonido ambiente.

Escribir escena por escena evita que un modelo pequeño (4B) se pierda o entre
en bucles repitiendo frases, garantiza exactamente N escenas y permite mostrar
el texto en vivo. El plan fijo con la ficha de personajes es la estrategia de
consistencia narrativa.
"""
import json
import re
import time

import config

TIPOS_SONIDO = [
    "lluvia", "tormenta", "viento", "bosque", "agua", "fuego", "noche",
    "ciudad", "espacio", "magia", "misterio", "terror", "multitud", "ambiente",
]

ESTRUCTURA = {
    5: ["presentación del protagonista y del lugar", "hecho que inicia el conflicto",
        "desarrollo y obstáculos", "clímax", "desenlace que cierra la historia"],
    4: ["presentación", "inicio del conflicto", "clímax", "desenlace"],
}

SISTEMA = ("Eres un escritor profesional de cuentos ilustrados en español. "
           "Escribes prosa clara y variada, sin repetir frases.")

PLAN = """Planea un cuento del género «{genero}» a partir de esta idea: «{idea}».

Devuelve SOLO este JSON, en este orden:
{{
  "titulo": "título corto y atractivo, en español",
  "personajes": [
    {{"nombre": "...", "descripcion": "quién es, en español, máximo 20 palabras",
      "descripcion_visual_en": "IN ENGLISH, max 20 words: first WHAT it is (robot, cat, girl...), then fixed traits (size, colors, clothes)"}}
  ],
  "estilo_visual_en": "one detailed illustration style IN ENGLISH, max 12 words (e.g. 'detailed watercolor storybook illustration, warm light')",
  "escenario": "lugar principal, en español, máximo 15 palabras",
  "resumen_escenas": ["frase 1", "frase 2", "..."]
}}

Reglas:
- De 1 a 3 personajes; el primero es el protagonista. Sus rasgos visuales no cambian.
- "descripcion_visual_en" SIEMPRE empieza diciendo QUÉ ES el personaje, tal como aparece en la idea
  (p. ej. "a small white gardening robot with a round glass head...", "an orange tabby cat...").
  Si en la idea es un robot, un animal o una criatura, NUNCA lo describas como persona humana.
- "resumen_escenas" tiene EXACTAMENTE {n} frases (máximo 20 palabras cada una), en este orden: {estructura}.
- Contenido apto para todo público, aunque el género sea terror (suspenso, sin violencia gráfica)."""

ESCENA = """{contexto}

Escribe ahora SOLO la escena {i} de {n}: «{resumen}».
- Entre {minimo} y {maximo} palabras, en un solo párrafo, narrado en tercera persona, con tono de {genero}.
- Continúa lo que pasó en las escenas anteriores y usa los mismos nombres.
- No escribas título ni número de escena, no repitas frases y no adelantes lo que pasa después.{cierre}"""

ARTE = """Cuento: «{titulo}». Protagonista: {protagonista}.

{escenas}

Para CADA una de las {n} escenas devuelve SOLO este JSON:
{{"escenas": [
  {{"descripcion_visual_en": "what the illustration shows IN ENGLISH, max 25 words; call the protagonist by type (e.g. 'the little orange cat'), not by name",
    "sonido_en": "ambient sound or effect IN ENGLISH, max 12 words, no voices, no music",
    "sonido_tipo": "una de: {tipos}"}}
]}}
La lista "escenas" debe tener exactamente {n} elementos, en orden."""


class ErrorHistoria(Exception):
    pass


class _Atascado(Exception):
    pass


# ------------------------------------------------------------------ utilidades
def _guardar_fallo(contenido, motivo):
    """Guarda la respuesta que falló, como evidencia para el informe y para depurar."""
    try:
        from datetime import datetime
        carpeta = config.SALIDAS_DIR / "_fallos_texto"
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = carpeta / f"{datetime.now():%Y%m%d_%H%M%S_%f}.txt"
        ruta.write_text(f"MOTIVO: {motivo}\n\n{contenido}", encoding="utf-8-sig")
    except Exception:
        pass


def _json(texto):
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.S).strip()
    texto = re.sub(r"^```(?:json)?|```$", "", texto, flags=re.M).strip()
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fin == -1:
        raise json.JSONDecodeError("no hay objeto JSON", texto, 0)
    return json.loads(texto[inicio:fin + 1])


def _oraciones(texto):
    return [o.strip() for o in re.split(r"(?<=[.!?…])\s+", texto) if o.strip()]


def limpiar_escena(texto, maximo, minimo=0):
    """Quita títulos, comillas y frases repetidas; recorta al tope de palabras
    terminando en una oración completa."""
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.S)
    texto = re.sub(r"^\s*(\*\*)?(escena|página)\s*\d+[^\n]*?[:.\n]", "", texto, flags=re.I)
    texto = " ".join(texto.replace("*", "").split()).strip(' "«»')
    vistas, salida, palabras = set(), [], 0
    for o in _oraciones(texto):
        clave = re.sub(r"\W+", " ", o.lower()).strip()
        if clave in vistas:
            continue  # frase repetida: se descarta
        n = len(o.split())
        if salida and palabras + n > maximo:
            if palabras < minimo:  # oración muy larga: se toma solo lo que cabe
                salida.append(" ".join(o.split()[: maximo - palabras]).rstrip(",;:") + ".")
            break
        vistas.add(clave)
        salida.append(o)
        palabras += n
    resultado = " ".join(salida)
    if resultado and resultado[-1] not in ".!?…»\"":
        corte = max(resultado.rfind(c) for c in ".!?…")
        resultado = resultado[:corte + 1] if corte > len(resultado) // 2 else resultado + "."
    return resultado


def _repite_mucho(texto):
    """True si el texto en curso ya está repitiendo frases (bucle)."""
    oraciones = [re.sub(r"\W+", " ", o.lower()).strip() for o in _oraciones(texto)]
    return len(oraciones) >= 4 and len(set(oraciones)) <= len(oraciones) // 2


# ------------------------------------------------------------------ llamada al modelo
def _pedir(cliente, modelo, prompt, opciones, formato=None, al_trozo=None, ultima=False):
    """Una llamada en streaming. Devuelve (texto, estadísticas)."""
    partes, stats = [], None
    flujo = cliente.chat(
        model=modelo,
        messages=[{"role": "system", "content": SISTEMA}, {"role": "user", "content": prompt}],
        format=formato,
        stream=True,
        options=opciones,
        keep_alive=0 if ultima else "5m",  # al final se libera la RAM para Stable Diffusion
    )
    try:
        for trozo in flujo:
            partes.append(trozo["message"]["content"] or "")
            if trozo.get("done"):
                stats = {"tokens": trozo.get("eval_count") or 0,
                         "segundos": (trozo.get("eval_duration") or 0) / 1e9,
                         "motivo_fin": trozo.get("done_reason")}
                break
            texto = "".join(partes)
            if len(texto) > 400 and not texto[-300:].strip():
                raise _Atascado("el modelo se quedó generando espacios en blanco")
            if formato is None and _repite_mucho(texto):
                stats = {"tokens": 0, "segundos": 0, "motivo_fin": "repeticion"}
                break  # se corta el bucle; limpiar_escena quita lo repetido
            if al_trozo:
                al_trozo(texto)
    except _Atascado as e:
        _guardar_fallo("".join(partes), str(e))
        raise
    except Exception as e:
        _guardar_fallo("".join(partes), f"conexión interrumpida: {e}")
        raise _Atascado(f"la conexión con Ollama se interrumpió ({type(e).__name__})") from e
    if stats is None:
        _guardar_fallo("".join(partes), "la respuesta terminó sin señal de fin")
        raise _Atascado("la respuesta de Ollama terminó antes de tiempo (¿el PC se suspendió?)")
    return "".join(partes), stats


def _opciones(max_tokens, temperatura):
    return {"temperature": temperatura, "num_ctx": config.LLM_CONTEXTO, "num_predict": max_tokens,
            "repeat_penalty": config.LLM_PENALIZACION_REPETICION, "repeat_last_n": 256}


# ------------------------------------------------------------------ pasos
def _validar_plan(plan, n):
    if not isinstance(plan, dict) or not str(plan.get("titulo", "")).strip():
        raise ErrorHistoria("el plan no trae título")
    pers = [p for p in plan.get("personajes", []) if isinstance(p, dict) and p.get("nombre")]
    if not pers:
        raise ErrorHistoria("el plan no trae personajes")
    for p in pers:
        p["descripcion"] = str(p.get("descripcion", "")).strip()
        p["descripcion_visual_en"] = str(p.get("descripcion_visual_en", "")).strip() or p["nombre"]
    resumen = [str(r).strip() for r in plan.get("resumen_escenas", []) if str(r).strip()]
    if len(resumen) < n:
        raise ErrorHistoria(f"el plan trae {len(resumen)} escenas y se necesitan {n}")
    return {
        "titulo": str(plan["titulo"]).strip(),
        "personajes": pers[:3],
        "estilo_visual_en": str(plan.get("estilo_visual_en", "")).strip() or "storybook illustration",
        "escenario": str(plan.get("escenario", "")).strip(),
        "resumen_escenas": resumen[:n],
    }


def _contexto(plan, genero, escritas):
    pers = "\n".join(f"- {p['nombre']}: {p['descripcion']}" for p in plan["personajes"])
    guion = "\n".join(f"{i}. {r}" for i, r in enumerate(plan["resumen_escenas"], start=1))
    partes = [f"Cuento: «{plan['titulo']}» (género: {genero}).",
              f"Personajes:\n{pers}", f"Escenario: {plan['escenario']}", f"Plan del cuento:\n{guion}"]
    if escritas:
        partes.append("Escenas ya escritas:\n" + "\n".join(
            f"Escena {i}: {t}" for i, t in enumerate(escritas, start=1)))
    return "\n\n".join(partes)


def vista_previa(titulo, escritas, en_curso=""):
    """Markdown del cuento mientras se escribe."""
    partes = [f"## {titulo}"] if titulo else []
    partes += [f"**Escena {i}.** {t}" for i, t in enumerate(escritas, start=1)]
    if en_curso:
        partes.append(f"**Escena {len(escritas) + 1}.** {en_curso} ▌")
    return "\n\n".join(partes)


def generar_historia(idea, genero, modelo=None, temperatura=None, intentos=None, registro=None,
                     al_avanzar=None):
    """Genera la historia completa y la devuelve como dict.

    `registro`: lista opcional donde se anotan reintentos y avisos.
    `al_avanzar(markdown, segundos)`: se llama mientras el modelo escribe.
    """
    import ollama

    modelo = modelo or config.OLLAMA_MODEL
    temperatura = config.LLM_TEMPERATURA if temperatura is None else temperatura
    intentos = intentos or config.LLM_INTENTOS
    n = config.NUM_ESCENAS
    registro = registro if registro is not None else []
    cliente = ollama.Client(host=config.OLLAMA_HOST)
    t0 = time.perf_counter()
    total = {"tokens": 0, "segundos": 0.0}
    ultimo = [0.0]

    def avisar(md):
        ahora = time.perf_counter() - t0
        if al_avanzar and ahora - ultimo[0] >= 0.7:
            ultimo[0] = ahora
            al_avanzar(md, ahora)

    def sumar(stats):
        total["tokens"] += stats.get("tokens") or 0
        total["segundos"] += stats.get("segundos") or 0

    def con_reintentos(nombre, funcion):
        error = None
        for intento in range(1, intentos + 1):
            try:
                return funcion()
            except (_Atascado, ErrorHistoria, json.JSONDecodeError) as e:
                error = e
                registro.append(f"Texto ({nombre}), intento {intento}: {e}")
            except Exception as e:  # Ollama apagado, modelo no descargado, etc.
                raise ErrorHistoria(
                    f"No se pudo conectar con Ollama o con el modelo '{modelo}'. "
                    f"Verifique que Ollama esté abierto y que haya ejecutado 'ollama pull {modelo}'. "
                    f"Detalle: {e}") from e
        raise ErrorHistoria(f"Falló «{nombre}» tras {intentos} intentos: {error}")

    # ---------------------------------------------------------------- 1. Plan
    def pedir_plan():
        prompt = PLAN.format(idea=idea, genero=genero, n=n,
                             estructura="; ".join(f"{i}) {e}" for i, e in
                                                  enumerate(ESTRUCTURA.get(n, ESTRUCTURA[5]), 1)))
        avisar("_Planeando el cuento: título, personajes y escenas..._")
        texto, stats = _pedir(cliente, modelo, prompt, _opciones(700, temperatura), formato="json")
        sumar(stats)
        try:
            return _validar_plan(_json(texto), n)
        except (json.JSONDecodeError, ErrorHistoria) as e:
            _guardar_fallo(texto, f"plan inválido: {e}")
            raise

    plan = con_reintentos("plan", pedir_plan)
    avisar(vista_previa(plan["titulo"], []))

    # ---------------------------------------------------------------- 2. Escenas
    escritas = []
    mejor = {}  # mejor intento de cada escena, por si todos salen cortos
    tope = int(config.ESCENA_PALABRAS_MAX * 2.2)  # ~1,6 tokens por palabra en español + margen
    for i in range(1, n + 1):
        def pedir_escena(i=i):
            prompt = ESCENA.format(
                contexto=_contexto(plan, genero, escritas), i=i, n=n, resumen=plan["resumen_escenas"][i - 1],
                minimo=config.ESCENA_PALABRAS_MIN, maximo=config.ESCENA_PALABRAS_MAX, genero=genero,
                cierre="\n- Es la última escena: cierra la historia." if i == n else "")
            texto, stats = _pedir(cliente, modelo, prompt, _opciones(tope, temperatura),
                                  al_trozo=lambda t: avisar(vista_previa(plan["titulo"], escritas, t)))
            sumar(stats)
            limpio = limpiar_escena(texto, config.ESCENA_PALABRAS_MAX, config.ESCENA_PALABRAS_MIN)
            if len(limpio.split()) > len(mejor.get(i, "").split()):
                mejor[i] = limpio
            if len(limpio.split()) < config.ESCENA_PALABRAS_MIN // 2:
                _guardar_fallo(texto, f"escena {i} demasiado corta")
                raise ErrorHistoria(f"la escena {i} salió demasiado corta")
            return limpio

        try:
            escritas.append(con_reintentos(f"escena {i}", pedir_escena))
        except ErrorHistoria:
            if not mejor.get(i):
                raise
            registro.append(f"Escena {i}: se usa el mejor intento ({len(mejor[i].split())} palabras)")
            escritas.append(mejor[i])
        avisar(vista_previa(plan["titulo"], escritas))

    # ---------------------------------------------------------------- 3. Arte y sonido
    protagonista = plan["personajes"][0]["descripcion_visual_en"]

    def pedir_arte():
        prompt = ARTE.format(titulo=plan["titulo"], protagonista=protagonista, n=n, tipos=", ".join(TIPOS_SONIDO),
                             escenas="\n".join(f"Escena {i}: {t}" for i, t in enumerate(escritas, 1)))
        texto, stats = _pedir(cliente, modelo, prompt, _opciones(1000, 0.5), formato="json", ultima=True)
        sumar(stats)
        try:
            datos = _json(texto)
            lista = datos.get("escenas", []) if isinstance(datos, dict) else []
            if len(lista) < n:
                raise ErrorHistoria(f"llegaron {len(lista)} descripciones visuales de {n}")
            return lista[:n]
        except (json.JSONDecodeError, ErrorHistoria) as e:
            _guardar_fallo(texto, f"arte inválido: {e}")
            raise

    try:
        arte = con_reintentos("descripciones visuales", pedir_arte)
    except ErrorHistoria as e:
        registro.append(f"Se usan descripciones visuales genéricas: {e}")
        arte = [{} for _ in range(n)]
        try:  # libera la RAM aunque haya fallado
            cliente.chat(model=modelo, messages=[], keep_alive=0)
        except Exception:
            pass

    escenas = []
    for i, (texto, a) in enumerate(zip(escritas, arte), start=1):
        a = a if isinstance(a, dict) else {}
        tipo = str(a.get("sonido_tipo", "")).strip().lower()
        escenas.append({
            "numero": i,
            "texto": texto,
            "resumen": plan["resumen_escenas"][i - 1],
            "descripcion_visual_en": str(a.get("descripcion_visual_en", "")).strip()
                                     or f"{protagonista}, storybook scene {i}",
            "sonido_en": str(a.get("sonido_en", "")).strip() or "soft ambient background",
            "sonido_tipo": tipo if tipo in TIPOS_SONIDO else "ambiente",
        })

    historia = {k: plan[k] for k in ("titulo", "personajes", "estilo_visual_en", "escenario")}
    historia["escenas"] = escenas
    historia["_intentos"] = sum(1 for r in registro if "intento" in r) + 1
    if total["segundos"]:
        total["tokens_por_s"] = round(total["tokens"] / total["segundos"], 1)
    historia["_estadisticas_llm"] = total
    return historia
