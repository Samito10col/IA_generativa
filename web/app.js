/* Érase una IA · lógica de la página
   Habla con el servidor local (app.py) por /api y recibe los avances en vivo
   por Server-Sent Events. Sin librerías externas. */
"use strict";

const $ = (s) => document.querySelector(s);
const estado = {
  config: null,
  genero: null,          // {nombre, icono, color, ejemplo}
  cuento: null,          // cuento con URLs (cuando ya existe el texto completo)
  vivo: null,            // {titulo, escenas[], escribiendo} mientras se escribe
  indice: 0,
  seguir: true,          // seguir la escena que se está escribiendo
  trabajando: false,
  leyendo: false,        // modo "Leer todo el cuento"
  audioAlDia: new Set(), // escenas cuyo audio ya se pidió en esta sesión
  opciones: {},
};

// ------------------------------------------------------------------ utilidades
const escapar = (t) => String(t ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let temporizadorAviso;
function avisar(mensaje, ok = false) {
  const a = $("#aviso");
  a.textContent = mensaje;
  a.classList.toggle("ok", ok);
  a.hidden = false;
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => (a.hidden = true), ok ? 3500 : 8000);
}

async function api(ruta, opciones = {}) {
  const r = await fetch(ruta, {
    headers: { "Content-Type": "application/json" },
    ...opciones,
    body: opciones.body ? JSON.stringify(opciones.body) : undefined,
  });
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(datos.detail || `Error ${r.status}`);
  return datos;
}

function mostrarPantalla(nombre) {
  document.body.dataset.pantalla = nombre;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ------------------------------------------------------------------ portada
function pintarGeneros() {
  const izq = $("#generos-izq"), der = $("#generos-der");
  izq.innerHTML = der.innerHTML = "";
  estado.config.generos.forEach((g, i) => {
    const b = document.createElement("button");
    b.className = "pildora";
    b.style.setProperty("--color", g.color);
    b.textContent = g.nombre;
    b.addEventListener("click", () => elegirGenero(g));
    (i < Math.ceil(estado.config.generos.length / 2) ? izq : der).appendChild(b);
  });
}

function elegirGenero(g) {
  estado.genero = g;
  document.documentElement.style.setProperty("--acento", g.color || "#e4f46a");
  $("#genero-actual").textContent = g.nombre;
  $("#idea").placeholder = `Ej.: ${g.ejemplo || "una aventura inolvidable"}`;
  mostrarPantalla("taller");
  setTimeout(() => $("#idea").focus(), 400);
}

// ------------------------------------------------------------------ configuración
function pintarConfig() {
  const c = $("#config");
  const titulos = {
    estrategia: "Consistencia visual", modelo_imagen: "Modelo de imagen",
    modo_imagen: "Velocidad de imagen", modo_sonido: "Ambiente sonoro",
  };
  c.innerHTML = "";
  for (const [clave, def] of Object.entries(estado.config.opciones)) {
    estado.opciones[clave] = def.valor;
    const fs = document.createElement("fieldset");
    fs.innerHTML = `<legend>${titulos[clave] || clave}</legend>` + def.opciones.map((o) => `
      <label><input type="radio" name="${clave}" value="${o.id}" ${o.id === def.valor ? "checked" : ""}>
      <span>${escapar(o.nombre)}</span></label>`).join("");
    fs.addEventListener("change", (e) => (estado.opciones[clave] = e.target.value));
    c.appendChild(fs);
  }
  estado.opciones.semilla = estado.config.semilla;
  const fs = document.createElement("fieldset");
  fs.innerHTML = `<legend>Semilla</legend><input type="number" id="semilla" value="${estado.config.semilla}">`;
  fs.addEventListener("input", (e) => (estado.opciones.semilla = parseInt(e.target.value || "0", 10)));
  c.appendChild(fs);
}

// ------------------------------------------------------------------ libro
const totalEscenas = () => estado.config?.escenas || 5;

function datosEscena(i) {
  const c = estado.cuento, v = estado.vivo;
  const escribiendo = !c && v && v.escribiendo && i === v.escenas.length - 1;
  return {
    titulo: c?.titulo || v?.titulo || "",
    texto: c?.escenas[i]?.texto ?? v?.escenas?.[i] ?? "",
    imagen: c?.escenas[i]?.imagen || null,
    audio: c?.escenas[i]?.audio || {},
    escribiendo,
  };
}

function pintarPagina() {
  const i = estado.indice, n = totalEscenas(), d = datosEscena(i);
  const hayAlgo = estado.cuento || estado.vivo;

  $("#titulo-cuento").textContent = d.titulo || (hayAlgo ? "Pensando un título..." : "Érase una IA");
  $("#capitulo").textContent = hayAlgo ? `Escena ${i + 1} de ${n}` : "Tu cuento comenzará aquí";
  $("#folio-izq").textContent = hayAlgo ? String(i * 2 + 1) : "";
  $("#folio-der").textContent = hayAlgo ? String(i * 2 + 2) : "";

  const texto = $("#texto");
  if (d.texto) {
    texto.innerHTML = `<p class="relato">${escapar(d.texto)}${d.escribiendo ? '<span class="cursor"></span>' : ""}</p>`;
    if (d.escribiendo) texto.scrollTop = texto.scrollHeight;
  } else if (hayAlgo) {
    texto.innerHTML = `<p class="vacio">${estado.trabajando ? "Esta página se escribirá en un momento..." : "Esta página quedó en blanco."}</p>`;
  }

  // ilustración
  const img = $("#ilustracion"), espera = $("#espera"), lienzo = $("#lienzo");
  if (d.imagen) {
    if (img.getAttribute("src") !== d.imagen) img.src = d.imagen;
    img.alt = `Ilustración de la escena ${i + 1}`;
    img.hidden = false; espera.hidden = true; lienzo.classList.remove("cargando");
  } else {
    img.hidden = true; img.removeAttribute("src"); espera.hidden = false;
    const ilustrando = estado.trabajando && estado.cuento;
    lienzo.classList.toggle("cargando", Boolean(ilustrando));
    $("#espera-texto").textContent = !hayAlgo ? "Aquí aparecerá la ilustración"
      : ilustrando ? "Pintando la ilustración..."
      : estado.trabajando ? "La ilustración llegará cuando termine el texto" : "Sin ilustración";
  }

  // audio
  const audioListo = Boolean(estado.cuento?.id) && Boolean(d.texto) && !estado.trabajando;
  $("#escuchar").disabled = !audioListo || estado.leyendo;
  $("#leer-todo").disabled = !audioListo;
  const nota = $("#nota-audio");
  nota.hidden = !(estado.trabajando && estado.cuento);
  nota.textContent = "El audio estará disponible al terminar las ilustraciones.";
  const rep = $("#reproductor");
  if (d.audio.mezcla) {
    if (rep.getAttribute("src") !== d.audio.mezcla) rep.src = d.audio.mezcla;
    rep.hidden = false;
    $("#pistas").hidden = false;
    $("#solo-voz").src = d.audio.voz || "";
    $("#solo-ambiente").src = d.audio.ambiente || "";
  } else {
    rep.pause(); rep.hidden = true; rep.removeAttribute("src");
    $("#pistas").hidden = true;
  }
  if (!estado.leyendo) {
    $("#escuchar").classList.remove("sonando");
    etiqueta("#escuchar", d.audio.mezcla ? "Escuchar de nuevo" : "Escuchar");
  }
  etiqueta("#leer-todo", estado.leyendo ? "Detener lectura" : "Leer todo el cuento");
  $("#leer-todo").classList.toggle("sonando", estado.leyendo);

  pintarPuntos();
  $("#anterior").disabled = i === 0;
  $("#siguiente").disabled = i >= n - 1;
}

function pintarPuntos() {
  const cont = $("#puntos"), n = totalEscenas();
  cont.innerHTML = "";
  for (let i = 0; i < n; i++) {
    const d = datosEscena(i), b = document.createElement("button");
    b.className = "punto" + (d.texto ? " escrito" : "") + (d.imagen ? " ilustrado" : "") + (i === estado.indice ? " actual" : "");
    b.setAttribute("aria-label", `Ir a la escena ${i + 1}`);
    b.addEventListener("click", () => irA(i, true));
    cont.appendChild(b);
  }
}

function irA(i, manual = false) {
  const n = totalEscenas();
  i = Math.max(0, Math.min(n - 1, i));
  if (i === estado.indice) return;
  if (manual) { estado.seguir = false; if (estado.leyendo) detenerLectura(); }
  const hoja = $("#hoja");
  hoja.className = "hoja " + (i > estado.indice ? "adelante" : "atras");
  void hoja.offsetWidth;                       // reinicia la animación
  estado.indice = i;
  setTimeout(pintarPagina, 260);               // el contenido cambia a mitad del giro
  setTimeout(() => (hoja.className = "hoja"), 700);
}

// ------------------------------------------------------------------ crear cuento
async function crear() {
  const idea = $("#idea").value.trim();
  if (!idea) { avisar("Escribe primero la idea de tu cuento."); $("#idea").focus(); return; }

  estado.cuento = null;
  estado.vivo = { titulo: "", escenas: [], escribiendo: true };
  estado.indice = 0; estado.seguir = true; estado.trabajando = true;
  $("#crear").disabled = true; $("#crear").textContent = "Creando...";
  $("#ver-detalles").disabled = true;
  $("#progreso").hidden = false;
  progreso(0.01, "Preparando la pluma...");
  pintarPagina();

  let trabajo;
  try {
    ({ trabajo } = await api("/api/generar", {
      method: "POST",
      body: { idea, genero: estado.genero.nombre, ...estado.opciones },
    }));
  } catch (e) {
    terminar(); avisar(e.message); return;
  }

  const fuente = new EventSource(`/api/progreso/${trabajo}`);
  fuente.onmessage = (m) => manejarEvento(JSON.parse(m.data));
  fuente.addEventListener("fin", () => { fuente.close(); terminar(); });
  fuente.onerror = () => {
    if (fuente.readyState === EventSource.CLOSED) return;
    fuente.close(); terminar();
    avisar("Se perdió la conexión con el servidor. Revisa la consola donde corre app.py.");
  };
}

function manejarEvento(ev) {
  switch (ev.tipo) {
    case "progreso":
      progreso(ev.f, ev.m);
      break;
    case "texto":
      estado.vivo = ev;
      if (estado.seguir && ev.escenas.length) estado.indice = ev.escenas.length - 1;
      pintarPagina();
      break;
    case "historia":
      estado.cuento = ev.cuento;
      if (estado.seguir) estado.indice = 0;
      estado.seguir = true;
      pintarPagina();
      break;
    case "imagen":
      if (estado.cuento) estado.cuento.escenas[ev.indice].imagen = ev.url;
      if (estado.seguir && ev.indice !== estado.indice) irA(ev.indice); else pintarPagina();
      break;
    case "listo":
      estado.cuento = ev.cuento;
      estado.trabajando = false;
      progreso(1, "¡Tu cuento está listo! Usa «Escuchar» o «Leer todo el cuento».");
      $("#ver-detalles").disabled = false;
      irA(0); pintarPagina();
      avisar(`«${ev.cuento.titulo}» está listo.`, true);
      break;
    case "error":
      estado.trabajando = false;
      progreso(0, "No se pudo terminar el cuento.");
      avisar(ev.mensaje);
      pintarPagina();
      break;
  }
}

function progreso(f, mensaje) {
  $("#progreso-texto").textContent = mensaje;
  $("#progreso-barra").style.width = `${Math.round(Math.max(0, Math.min(1, f)) * 100)}%`;
}

function terminar() {
  estado.trabajando = false;
  $("#crear").disabled = false; $("#crear").textContent = "Crear cuento";
  pintarPagina();
}

// ------------------------------------------------------------------ audio
const ICONO_LIBRO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 6C9 4 5 4 2 5v14c3-1 7-1 10 1 3-2 7-2 10-1V5c-3-1-7-1-10 1z"/><path d="M12 6v14"/></svg>';

function etiqueta(selector, texto) {
  const span = document.querySelector(`${selector} span`);
  if (span) span.textContent = texto;
}

/** Pide al servidor el audio de la escena i (lo genera si no existe o está desactualizado). */
async function obtenerAudio(i) {
  const c = estado.cuento;
  if (!estado.audioAlDia.has(i)) {
    c.escenas[i].audio = await api(`/api/cuentos/${encodeURIComponent(c.id)}/audio/${i}`, {
      method: "POST",
      body: { modo_sonido: estado.opciones.modo_sonido, semilla: estado.opciones.semilla },
    });
    estado.audioAlDia.add(i);
  }
  return c.escenas[i].audio;
}

/** Reproduce lo que tenga el reproductor; termina cuando acaba o se detiene. */
function reproducir() {
  const rep = $("#reproductor");
  rep.currentTime = 0;
  return new Promise((resolver) => {
    const fin = () => { rep.removeEventListener("ended", fin); rep.removeEventListener("pause", fin); resolver(); };
    rep.addEventListener("ended", fin);
    rep.addEventListener("pause", fin);
    rep.play().catch(fin);
  });
}

async function escuchar() {
  const i = estado.indice;
  if (!estado.cuento?.id) return;
  const boton = $("#escuchar");
  boton.disabled = true; etiqueta("#escuchar", "Preparando la voz...");
  try {
    await obtenerAudio(i);
  } catch (e) {
    avisar(e.message); boton.disabled = false; etiqueta("#escuchar", "Escuchar"); return;
  }
  if (estado.indice !== i) return;           // el usuario ya cambió de página
  pintarPagina();
  boton.classList.add("sonando"); etiqueta("#escuchar", "Sonando...");
  await reproducir();
  boton.classList.remove("sonando"); etiqueta("#escuchar", "Escuchar de nuevo");
}

const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

/** Modo cuentacuentos: narra todas las escenas seguidas y pasa las páginas solo. */
async function leerTodo() {
  if (estado.leyendo) { detenerLectura(); return; }
  if (!estado.cuento?.id) return;
  estado.leyendo = true;
  const n = estado.cuento.escenas.length;
  pintarPagina();
  for (let i = 0; i < n && estado.leyendo; i++) {
    if (i !== estado.indice) { irA(i); await esperar(750); }
    etiqueta("#escuchar", "Preparando la voz...");
    try {
      await obtenerAudio(i);
    } catch (e) { avisar(e.message); break; }
    if (!estado.leyendo) break;
    pintarPagina();
    etiqueta("#escuchar", "Sonando...");
    $("#escuchar").classList.add("sonando");
    if (i + 1 < n) obtenerAudio(i + 1).catch(() => {});   // prepara la siguiente mientras suena
    await reproducir();
    $("#escuchar").classList.remove("sonando");
    if (estado.leyendo && i + 1 < n) await esperar(600);
  }
  estado.leyendo = false;
  pintarPagina();
}

function detenerLectura() {
  if (!estado.leyendo) return;
  estado.leyendo = false;
  $("#reproductor").pause();
  pintarPagina();
}

// ------------------------------------------------------------------ mis cuentos
async function abrirEstante() {
  const est = $("#estante");
  est.innerHTML = '<p class="vacio">Cargando...</p>';
  $("#dlg-cuentos").showModal();
  try {
    const lista = await api("/api/cuentos");
    if (!lista.length) { est.innerHTML = '<p class="vacio">Todavía no hay cuentos guardados.</p>'; return; }
    est.innerHTML = "";
    for (const c of lista) {
      const b = document.createElement("button");
      b.className = "tarjeta";
      b.innerHTML = (c.portada ? `<img src="${c.portada}" alt="">` : `<span class="sin-portada">${ICONO_LIBRO}</span>`) +
        `<div><strong>${escapar(c.titulo)}</strong><small>${escapar(c.genero || "")} · ${escapar((c.fecha || "").slice(0, 10))}</small></div>`;
      b.addEventListener("click", () => abrirCuento(c.id));
      est.appendChild(b);
    }
  } catch (e) { est.innerHTML = `<p class="vacio">${escapar(e.message)}</p>`; }
}

async function abrirCuento(id) {
  if (estado.trabajando) { avisar("Espera a que termine el cuento que se está creando."); return; }
  try {
    const c = await api(`/api/cuentos/${encodeURIComponent(id)}`);
    $("#dlg-cuentos").close();
    const g = estado.config.generos.find((x) => x.nombre === c.genero) || estado.config.generos[0];
    elegirGenero(g);
    $("#idea").value = c.idea || "";
    detenerLectura();
    estado.cuento = c; estado.vivo = null; estado.indice = 0; estado.audioAlDia = new Set();
    $("#ver-detalles").disabled = false;
    $("#progreso").hidden = true;
    pintarPagina();
  } catch (e) { avisar(e.message); }
}

// ------------------------------------------------------------------ detalles
function verDetalles() {
  const c = estado.cuento; if (!c) return;
  const m = c.metadatos || {}, t = m.tiempos_s || {}, o = m.opciones || {}, h = m.hardware || {}, llm = m.estadisticas_llm || {};
  const fila = (k, v) => `<tr><td>${k}</td><td>${escapar(v ?? "—")}</td></tr>`;
  const audios = Object.entries(m.audio || {}).map(([k, a]) =>
    fila(`Escena ${k}`, `${a.fuente_sonido} · voz ${a.tiempos_s?.voz}s · ambiente ${a.tiempos_s?.sonido}s`)).join("");
  $("#detalles").innerHTML = `
    <h3>Cuento</h3><table>
      ${fila("Título", c.titulo)}${fila("Idea", c.idea)}${fila("Género", c.genero)}
      ${fila("Personajes", (c.personajes || []).map((p) => `${p.nombre}: ${p.descripcion}`).join(" · "))}
      ${fila("Palabras por escena", (m.palabras_por_escena || []).join(", "))}</table>
    <h3>Configuración</h3><table>
      ${fila("Modelo de texto", o.modelo_texto)}${fila("Modelo de imagen", o.modelo_imagen)}
      ${fila("Velocidad de imagen", o.modo_imagen)}${fila("Estrategia de consistencia", o.estrategia)}
      ${fila("Semilla", o.semilla)}</table>
    <h3>Tiempos</h3><table>
      ${fila("Texto", `${t.texto} s (${llm.tokens_por_s ?? "?"} tokens/s)`)}${fila("Imágenes", `${t.imagenes} s`)}
      ${fila("Total", `${t.total} s`)}${audios}</table>
    <h3>Equipo</h3><table>
      ${fila("Procesador", h.procesador)}${fila("RAM", h.ram_gb ? `${h.ram_gb} GB` : "")}${fila("GPU", h.gpu)}
      ${fila("Sistema", h.sistema)}</table>
    <h3>Avisos</h3><p>${(m.avisos || []).map(escapar).join("<br>") || "Ninguno"}</p>`;
  $("#dlg-detalles").showModal();
}

// ------------------------------------------------------------------ inicio
async function iniciar() {
  try {
    estado.config = await api("/api/config");
  } catch (e) {
    avisar("No se pudo hablar con el servidor. ¿Está corriendo app.py?"); return;
  }
  pintarGeneros();
  pintarConfig();
  pintarPagina();

  $("#volver").addEventListener("click", () => mostrarPantalla("portada"));
  $("#crear").addEventListener("click", crear);
  $("#usar-ejemplo").addEventListener("click", () => { $("#idea").value = estado.genero?.ejemplo || ""; });
  $("#toggle-config").addEventListener("click", (e) => {
    const abierto = $("#config").hidden;
    $("#config").hidden = !abierto;
    e.currentTarget.setAttribute("aria-expanded", String(abierto));
  });
  $("#anterior").addEventListener("click", () => irA(estado.indice - 1, true));
  $("#siguiente").addEventListener("click", () => irA(estado.indice + 1, true));
  $("#escuchar").addEventListener("click", escuchar);
  $("#leer-todo").addEventListener("click", leerTodo);
  $("#ver-detalles").addEventListener("click", verDetalles);
  document.querySelectorAll("[data-abrir='dlg-cuentos']").forEach((b) => b.addEventListener("click", abrirEstante));
  document.querySelectorAll("[data-cerrar]").forEach((b) =>
    b.addEventListener("click", () => b.closest("dialog").close()));
  $("#idea").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) crear(); });
  document.addEventListener("keydown", (e) => {
    if (document.body.dataset.pantalla !== "taller" || e.target.matches("textarea, input")) return;
    if (e.key === "ArrowRight") irA(estado.indice + 1, true);
    if (e.key === "ArrowLeft") irA(estado.indice - 1, true);
  });
}

iniciar();
