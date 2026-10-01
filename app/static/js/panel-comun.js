// ---------- ESTADO GLOBAL COMPARTIDO ----------
let token = localStorage.getItem("rifalo_token") || null;
let rol = localStorage.getItem("rifalo_rol") || null;
let MODALIDADES = [];
let SORTEOS_ABIERTOS_CACHE = {};
let SORT_CACHE = {};
let VEND_CACHE = {};
let REV_CACHE = {};
let VJUG_CACHE = {};
let RJUG_CACHE = {};
let JUGADORES_CACHE = {};
let SORT_ACTUAL = null;
let TAB_ACTUAL = null;
let JUGADOR_SORTEO_ELEGIDO = null;
let sorteo_edit_id = null;
let vendedor_edit_id = null;
let rev_edit_id = null;
let vjug_edit_id = null;
let rjug_edit_id = null;
let avisosTimer = null;
let refrescoTimer = null;
window.ACCIONES = window.ACCIONES || {};

const TABS_POR_ROL = {
  admin_principal: [["sorteos","Sorteos"],["buscador","Buscador"],["vendedores","Vendedores"],["pagos","Pagos a vendedores"],["jugadas","Jugadas"],["resumen","Resumen"],["balance","Balance"],["auditoria","Auditoria"]],
  admin: [["sorteos","Sorteos"],["buscador","Buscador"],["pagos","Pagos a vendedores"],["jugadas","Jugadas"],["resumen","Resumen"],["balance","Balance"],["auditoria","Auditoria"]],
  vendedor: [["vresumen","Mi resumen"],["vcargar","Cargar jugada"],["vpendientes","Aprobar"],["vjugadas","Mis jugadas"],["vrevendedores","Mis revendedores"],["vjugadores","Mis jugadores"],["resultados","Resultados"],["cobros","Mis cobros"]],
  revendedor: [["rsorteos","Sorteos"],["rcargar","Cargar jugada"],["rjugadas","Mis jugadas"],["rresumen","Mi resumen"],["rjugadores","Mis jugadores"],["resultados","Resultados"]],
  jugador: [["jsorteos","Sorteos"],["jcargar","Mi jugada"],["resultados","Resultados"]],
};

function cabeceras() { return { "Content-Type": "application/json", "Authorization": "Bearer " + token }; }

async function api(ruta, metodo, cuerpo) {
  const r = await fetch(ruta, { method: metodo, headers: cabeceras(), body: cuerpo ? JSON.stringify(cuerpo) : undefined });
  if (r.status === 401) { salir(); throw new Error("Sesion expirada, entra de nuevo"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail);
    throw new Error(msg || ("Error " + r.status));
  }
  return d;
}

function aviso(t, err) {
  const c = document.getElementById("mensaje");
  c.className = "mensaje " + (err ? "error" : "ok");
  c.textContent = t;
}

function regMsg(t, err) {
  const c = document.getElementById("reg-msg");
  c.className = "mensaje " + (err ? "error" : "ok");
  c.textContent = t;
}

function parseNumeros(texto) {
  return texto.split(/[,\s]+/).filter(x => x).map(x => parseInt(x, 10));
}

function fmtFecha(iso) {
  if (!iso) return "-";
  const p = String(iso).slice(0,10).split("-");
  if (p.length !== 3) return String(iso).slice(0,10);
  return p[2] + "-" + p[1] + "-" + p[0];
}

function aIsoFecha(txt) {
  txt = (txt || "").trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(txt)) return txt;
  const m = txt.match(/^(\d{2})-(\d{2})-(\d{4})$/);
  if (m) return m[3] + "-" + m[2] + "-" + m[1];
  return null;
}

function waLink(telefono, mensaje) {
  let t = (telefono || "").replace(/[\s\-\(\)\+]/g, "");
  if (!t) return null;
  if (!t.startsWith("54")) t = "54" + t;
  const msg = encodeURIComponent(mensaje || "");
  return "https://wa.me/" + t + (msg ? "?text=" + msg : "");
}

function nombreSorteo(s) {
  return (s.titulo || s.nombre_modalidad || s.modalidad || "");
}

// ---------- PREMIO CON NOMBRE (oculta el monto interno cuando hay premio_nombre) ----------
function tienePremioNombre(s) { return !!(s && s.premio_nombre); }

function etiquetaPozo(s) {
  if (!s) return "";
  if (s.premio_nombre) return "Premio: " + s.premio_nombre;
  const esVacante = Boolean(s.solo_participantes);
  return (esVacante ? "Pozo vacante $" : "$") + s.pozo;
}

// ---------- CARTEL LLAMATIVO (titulo grande + pozo o premio) ----------
function cartelSorteoHtml(s) {
  if (!s) return "Seleccioná un sorteo para ver el pozo actual";
  const titulo = nombreSorteo(s) || (s.modalidad || "");
  if (s.premio_nombre) {
    return (
      "<div style='font-size:22px;font-weight:bold;color:#fbbf24;line-height:1.1'>" + titulo + "</div>" +
      "<div style='font-size:13px;color:#94a3b8;margin-top:6px'>PREMIO</div>" +
      "<div style='font-size:26px;font-weight:bold;color:#22c55e'>" + s.premio_nombre + "</div>" +
      "<div style='font-size:12px;color:#cbd5e1;margin-top:4px'>Sorteo #" + s.id + " · " + s.horario + " · " + fmtFecha(s.fecha) + "</div>"
    );
  }
  const esVacante = Boolean(s.solo_participantes);
  const rotulo = esVacante ? "POZO VACANTE" : "POZO";
  const colorPozo = esVacante ? "#22c55e" : "#FFC107";
  const arranque = esVacante ? "<div style='font-size:13px;color:#86efac;margin-top:2px'>Arranca en $" + (s.pozo_inicial ?? s.pozo) + "</div>" : "";
  return (
    "<div style='font-size:22px;font-weight:bold;color:#fbbf24;line-height:1.1'>" + titulo + "</div>" +
    "<div style='font-size:30px;font-weight:bold;color:" + colorPozo + ";margin:4px 0'>$" + s.pozo + "</div>" +
    "<div style='font-size:12px;color:#cbd5e1'>" + rotulo + " · Sorteo #" + s.id + " · " + s.horario + " · " + fmtFecha(s.fecha) + "</div>" +
    arranque
  );
}

function pintarPozo(divId, s) {
  const c = document.getElementById(divId);
  if (!c) return;
  c.style.display = "block";
  c.innerHTML = cartelSorteoHtml(s);
}

// ---------- SUBIR IMAGEN (comprime antes de mandar al backend) ----------
function comprimirImagen(file, maxDim, calidad) {
  maxDim = maxDim || 900;
  calidad = calidad || 0.82;
  return new Promise((resolve, reject) => {
    if (!file) { resolve(null); return; }
    if (!file.type || !file.type.startsWith("image/")) { reject(new Error("Elegí un archivo de imagen (jpg o png)")); return; }
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("No se pudo leer la imagen"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("El archivo no es una imagen valida"));
      img.onload = () => {
        let w = img.width, h = img.height;
        if (w > h && w > maxDim) { h = Math.round(h * maxDim / w); w = maxDim; }
        else if (h >= w && h > maxDim) { w = Math.round(w * maxDim / h); h = maxDim; }
        const canvas = document.createElement("canvas");
        canvas.width = w; canvas.height = h;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, w, h);
        let dataUri;
        try { dataUri = canvas.toDataURL("image/jpeg", calidad); }
        catch (e) { reject(new Error("No se pudo comprimir la imagen")); return; }
        resolve(dataUri);
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

// ---------- GRILLA DE RIFA (numeros 00-99, libres/ocupados) ----------
function rutaOcupados() {
  if (rol === "jugador") return "/jugador/sorteos/";
  if (rol === "vendedor") return "/vendedor/sorteos/";
  if (rol === "revendedor") return "/revendedor/sorteos/";
  return null;
}

function asegurarDivGrilla(pref) {
  const input = document.getElementById(pref + "-numeros");
  if (!input) return null;
  let div = document.getElementById(pref + "-grilla");
  if (!div) {
    div = document.createElement("div");
    div.id = pref + "-grilla";
    div.style.cssText = "display:none;margin:8px 0;";
    input.parentNode.insertBefore(div, input.nextSibling);
  }
  return div;
}

async function refrescarGrillaRifa(idSelect, s) {
  const pref = idSelect.replace("-sorteo", "");
  const div = asegurarDivGrilla(pref);
  if (!div) return;
  const esRifaUnico = s && s.modalidad === "rifa" && s.cantidad_numeros === 1;
  if (!esRifaUnico) { div.style.display = "none"; div.innerHTML = ""; return; }
  const base = rutaOcupados();
  if (!base) { div.style.display = "none"; return; }
  try {
    const d = await api(base + s.id + "/ocupados", "GET");
    const ocupados = new Set(d.ocupados || []);
    let html = "<div class='chico' style='margin-bottom:4px'>Elegí tu número tocando un casillero verde. Los rojos ya están jugados (no se repiten).</div>";
    html += "<div style='display:grid;grid-template-columns:repeat(10,1fr);gap:3px;'>";
    for (let n = 0; n < 100; n++) {
      const lab = String(n).padStart(2, "0");
      if (ocupados.has(n)) {
        html += "<div style='background:#7f1d1d;color:#fca5a5;text-align:center;padding:6px 0;border-radius:4px;font-size:12px;cursor:not-allowed'>" + lab + "</div>";
      } else {
        html += "<div onclick=\"tocarNumeroRifa('" + pref + "'," + n + ")\" style='background:#14532d;color:#bbf7d0;text-align:center;padding:6px 0;border-radius:4px;font-size:12px;cursor:pointer'>" + lab + "</div>";
      }
    }
    html += "</div>";
    div.innerHTML = html;
    div.style.display = "block";
  } catch (e) { div.style.display = "none"; }
}

function tocarNumeroRifa(pref, n) {
  const input = document.getElementById(pref + "-numeros");
  if (input) input.value = String(n).padStart(2, "0");
}

// ---------- MODO SORTEO (ficha admin) ----------
function pintarModo() {
  const caja = document.getElementById("zona-modo");
  if (!SORT_ACTUAL) { caja.style.display = "none"; caja.innerHTML = ""; return; }
  const s = SORT_CACHE[SORT_ACTUAL];
  caja.style.display = "block";
  if (!s) {
    caja.innerHTML = "Sorteo #" + SORT_ACTUAL + " seleccionado. <button class='secundario' onclick='refrescarModo()'>Actualizar ficha</button> <button class='peligro' onclick='salirSorteo()'>Salir del sorteo</button>";
    return;
  }
  caja.innerHTML =
    "<b>FICHA DEL SORTEO #" + s.id + (s.titulo ? " - " + s.titulo : "") + "</b><br>" +
    "Modalidad: " + s.modalidad + " | Horario oficial: " + s.horario + " | Dia: " + fmtFecha(s.fecha) + " | Cierre para anotarse: " + (s.hora_cierre || "sin limite") + "<br>" +
    "Estado: " + s.estado + (s.busqueda_agotada ? " (busqueda agotada, carga manual)" : "") + " | Precio jugada: $" + s.precio_jugada + " | Casa: " + s.casa_pct + "% | Vendedores: " + s.vendedor_pct + "%<br>" +
    (s.premio_nombre ? ("Premio: " + s.premio_nombre + "<br>") : "") +
    "Pozo mostrado: $" + s.pozo + " | <b>Pozo cubierto (sobrantes): $" + s.pozo_cubierto + " de $" + s.costo + "</b> " + (s.costo_cubierto ? "✔ CUBIERTO" : "✘ SIN CUBRIR") + "<br>" +
    "Vendido total: $" + s.recaudado + " | Resultados: " + (s.resultados || "sin cargar") + "<br>" +
    "<span class='chico'>Las pestanas Jugadas, Resumen, Balance, Pagos y Auditoria muestran solo este sorteo.</span> " +
    "<button class='secundario' onclick='refrescarModo()'>Actualizar ficha</button> <button class='peligro' onclick='salirSorteo()'>Salir del sorteo</button>";
}

async function refrescarModo() {
  try {
    const ss = await api("/admin/sorteos", "GET");
    ss.forEach(x => { SORT_CACHE[x.id] = x; });
    pintarModo();
  } catch (e) { /* ignora */ }
}

async function seleccionarSorteo(id) {
  SORT_ACTUAL = id;
  if (!SORT_CACHE[id]) {
    try { const ss = await api("/admin/sorteos", "GET"); ss.forEach(s => { SORT_CACHE[s.id] = s; }); } catch (e) { /* ignora */ }
  }
  pintarModo();
  aviso("Modo sorteo activado: las pestanas Jugadas, Resumen, Balance, Pagos y Auditoria muestran solo el sorteo #" + id);
  if (TAB_ACTUAL) irTab(TAB_ACTUAL);
}

function salirSorteo() {
  SORT_ACTUAL = null;
  pintarModo();
  aviso("Saliste del modo sorteo: el panel vuelve a mostrar todo");
  if (TAB_ACTUAL) irTab(TAB_ACTUAL);
}

// ---------- AVISOS ----------
async function cargarAvisos() {
  try {
    const as = await api("/admin/avisos", "GET");
    const esAdmin = (rol === "admin_principal" || rol === "admin");
    document.getElementById("zona-avisos").innerHTML = as.map(a =>
      "<div class='aviso-box'>" + a.texto + (esAdmin ? " <button class='peligro' onclick='borrarAviso(" + a.id + ")'>X</button>" : "") + "</div>"
    ).join("");
  } catch (e) { /* sin sesion o sin permiso */ }
}

async function borrarAviso(id) {
  try { await api("/admin/avisos/" + id, "DELETE"); cargarAvisos(); }
  catch (e) { aviso(e.message, true); }
}

// ---------- SESION ----------
async function login() {
  const cuerpo = { usuario: document.getElementById("login-usuario").value, password: document.getElementById("login-password").value };
  const f = document.getElementById("login-2fa").value;
  if (f) cuerpo.codigo_2fa = f;
  try {
    const r = await fetch("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });
    const d = await r.json();
    if (!d.token) throw new Error(d.detail || "Credenciales incorrectas");
    token = d.token; rol = d.rol;
    localStorage.setItem("rifalo_token", token);
    localStorage.setItem("rifalo_rol", rol);
    localStorage.setItem("rifalo_nombre", d.nombre);
    SORT_ACTUAL = null;
    mostrarPanel();
  } catch (e) {
    const c = document.getElementById("login-error");
    c.className = "mensaje error"; c.textContent = e.message;
  }
}

function mostrarRegistro() { document.getElementById("form-registro").style.display = "block"; }

async function registrarJugador() {
  const cuerpo = {
    usuario: document.getElementById("reg-usuario").value,
    password: document.getElementById("reg-password").value,
    nombre: document.getElementById("reg-nombre").value,
    telefono: document.getElementById("reg-telefono").value,
    codigo_vendedor: document.getElementById("reg-codigo").value,
    datos_cobro: document.getElementById("reg-cobro").value,
    cobro_transferencia: document.getElementById("reg-transferencia").checked,
  };
  try {
    const r = await fetch("/auth/registro-jugador", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) {
      const det = typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail);
      if (det.includes("ya existe")) {
        regMsg("El usuario ya existe, elegi otro.", true);
      } else {
        regMsg(det || "Error de registro", true);
      }
      return;
    }
    regMsg("Registro listo: ya podes ingresar con tu usuario y contrasenia. Tus premios se acreditan en tu alias/CBU.");
  } catch (e) { regMsg(e.message, true); }
}

function salir() {
  token = null; rol = null;
  localStorage.removeItem("rifalo_token"); localStorage.removeItem("rifalo_rol");
  document.getElementById("zona-panel").style.display = "none";
  document.getElementById("zona-login").style.display = "block";
}

// ---------- CARGA DE SECCIONES POR ROL ----------
async function cargarSeccionesRol() {
  const cont = document.getElementById("contenedor-secciones");
  const mapa = { admin_principal: "admin", admin: "admin", vendedor: "vendedor", revendedor: "revendedor", jugador: "jugador" };
  const parte = mapa[rol] || "jugador";
  try {
    const r = await fetch("/static/partes/" + parte + ".html");
    cont.innerHTML = await r.text();
  } catch (e) {
    cont.innerHTML = "<p class='mensaje error'>No se pudo cargar la interfaz del rol.</p>";
  }
}

function mostrarPanel() {
  document.getElementById("zona-login").style.display = "none";
  document.getElementById("zona-panel").style.display = "block";
  document.getElementById("panel-usuario").textContent = "- " + (localStorage.getItem("rifalo_nombre") || "") + " (" + rol + ")";
  const barra = document.getElementById("barra-tabs");
  const tabs = TABS_POR_ROL[rol] || [];
  barra.innerHTML = tabs.map(t => "<button id='tab-" + t[0] + "' onclick=\"irTab('" + t[0] + "')\">" + t[1] + "</button>").join("") + "<button class='peligro' onclick='salir()'>Salir</button>";
  cargarSeccionesRol().then(() => {
    pintarModo();
    cargarAvisos();
    if (!avisosTimer) { avisosTimer = setInterval(cargarAvisos, 60000); }
    if (!refrescoTimer) {
      refrescoTimer = setInterval(() => {
        if (document.hidden) return;
        if (TAB_ACTUAL === "jsorteos") cargarJSorteos();
        else if (TAB_ACTUAL === "rsorteos") cargarRSorteos();
        else if (TAB_ACTUAL === "buscador") cargarEstadoBuscador();
      }, 30000);
    }
    irTab(tabs[0][0]);
  });
}

function irTab(nombre) {
  TAB_ACTUAL = nombre;
  document.querySelectorAll("#contenedor-secciones .tarjeta").forEach(s => { s.style.display = "none"; });
  const seccion = document.getElementById("seccion-" + nombre);
  if (seccion) seccion.style.display = "block";
  document.querySelectorAll("#barra-tabs button").forEach(b => { b.className = ""; });
  const tab = document.getElementById("tab-" + nombre);
  if (tab) tab.className = "activa";
  const acc = window.ACCIONES[nombre];
  if (acc) acc();
}

// ---------- SELECTS COMPARTIDOS ----------
async function llenarSelectSorteos(ruta, idSelect) {
  try {
    const previo = document.getElementById(idSelect).value;
    const sorteos = await api(ruta, "GET");
    SORTEOS_ABIERTOS_CACHE[idSelect] = {};
    sorteos.forEach(s => { SORTEOS_ABIERTOS_CACHE[idSelect][s.id] = s; });
    document.getElementById(idSelect).innerHTML = sorteos.map(s =>
      "<option value='" + s.id + "'>#" + s.id + " " + nombreSorteo(s) + " " + s.horario + " " + fmtFecha(s.fecha) + " - $" + s.precio_jugada + " - " + etiquetaPozo(s) + " - " + s.estado + " - cierre " + (s.hora_cierre || "sin limite") + (s.solo_participantes ? " (VACANTE)" : "") + (s.reprogramando ? " (REPROGRAMANDO)" : "") + "</option>"
    ).join("") || "<option value=''>No hay sorteos abiertos</option>";
    if (previo) document.getElementById(idSelect).value = previo;
    const idImg = idSelect.replace("-sorteo", "-imagen");
    pintarReglasSelect(idSelect, idSelect.replace("-sorteo", "-reglas"), idImg);
  } catch (e) { aviso(e.message, true); }
}

function pintarReglasSelect(idSelect, idCaja, idImagen) {
  const id = document.getElementById(idSelect).value;
  const s = SORTEOS_ABIERTOS_CACHE[idSelect] && SORTEOS_ABIERTOS_CACHE[idSelect][id];
  const caja = document.getElementById(idCaja);
  if (caja) caja.textContent = s ? (nombreSorteo(s) + ": " + (s.detalle || s.reglas) + " | Precio jugada: $" + s.precio_jugada + " | " + etiquetaPozo(s) + " | Estado: " + s.estado + " | Cierre para anotarse: " + (s.hora_cierre || "sin limite") + (s.reprogramando ? " | REPROGRAMANDO: aguarda nuevo horario" : "")) : "";
  const img = document.getElementById(idImagen);
  if (img) {
    if (s && s.imagen_url) { img.src = s.imagen_url; img.style.display = "block"; }
    else { img.style.display = "none"; }
  }
  if (idSelect === "j-sorteo") {
    JUGADOR_SORTEO_ELEGIDO = id ? parseInt(id) : null;
    pintarPozo("pozo-jugador", s || null);
  }
  if (idSelect === "v-sorteo") filtrarJugadoresSorteo("v", s);
  if (idSelect === "r-sorteo") filtrarJugadoresSorteo("r", s);
  refrescarGrillaRifa(idSelect, s);
}

async function cargarSelectJugadores(pref) {
  const ruta = pref === "v" ? "/vendedor/jugadores" : "/revendedor/jugadores";
  try {
    const js = await api(ruta, "GET");
    JUGADORES_CACHE[pref] = js;
    const sel = document.getElementById(pref + "-jugador-select");
    sel.innerHTML = "<option value=''>Jugador no registrado (escribir nombre abajo)</option>" +
      js.filter(j => j.activo).map(j => "<option value='" + j.id + "'>" + j.nombre + " (" + j.usuario + ")</option>").join("");
    document.getElementById(pref + "-jugador").disabled = false;
    const idSel = pref + "-sorteo";
    const sSel = SORTEOS_ABIERTOS_CACHE[idSel] && SORTEOS_ABIERTOS_CACHE[idSel][document.getElementById(idSel).value];
    filtrarJugadoresSorteo(pref, sSel || null);
  } catch (e) { /* ignora */ }
}

function filtrarJugadoresSorteo(pref, s) {
  const todos = JUGADORES_CACHE[pref] || [];
  const sel = document.getElementById(pref + "-jugador-select");
  if (!sel) return;
  let lista = todos;
  if (s && s.solo_participantes && s.participantes && s.participantes.length) {
    lista = todos.filter(j => s.participantes.includes(j.nombre));
  }
  sel.innerHTML = "<option value=''>Jugador no registrado (escribir nombre abajo)</option>" +
    lista.filter(j => j.activo).map(j => "<option value='" + j.id + "'>" + j.nombre + " (" + j.usuario + ")</option>").join("");
}

function toggleJugadorManual(pref) {
  const sel = document.getElementById(pref + "-jugador-select");
  const input = document.getElementById(pref + "-jugador");
  if (sel.value) {
    input.value = "";
    input.disabled = true;
  } else {
    input.disabled = false;
  }
}

// ---------- LINKS DE REGISTRO Y WHATSAPP ----------
async function cargarLinkVendedor() {
  try {
    const me = await api("/auth/me", "GET");
    document.getElementById("v-link").value = window.location.origin + "/panel?codigo=" + (me.codigo || "");
  } catch (e) { /* ignora */ }
}

async function cargarLinkRevendedor() {
  try {
    const me = await api("/auth/me", "GET");
    document.getElementById("r-link").value = window.location.origin + "/panel?codigo=" + (me.codigo || "");
  } catch (e) { /* ignora */ }
}

function copiarLink(idInput) {
  const input = document.getElementById(idInput);
  input.select();
  input.setSelectionRange(0, 99999);
  document.execCommand("copy");
  aviso("Link copiado: pegalo donde quieras compartirlo");
}

function mostrarTodosWhatsApp(pref) {
  const cache = pref === "v" ? VJUG_CACHE : RJUG_CACHE;
  const contId = pref === "v" ? "vjugadores-wa-links" : "rjugadores-wa-links";
  const cont = document.getElementById(contId);
  if (!cont) return;
  const jugadores = Object.values(cache).filter(j => j.activo && j.telefono);
  if (!jugadores.length) {
    cont.innerHTML = "<div class='wa-links'>No hay jugadores activos con telefono cargado.</div>";
    return;
  }
  const msg = "Hola {nombre}, te escribo de RIFALO.";
  let html = "<div class='wa-links'><b>Hace click en cada link para abrir WhatsApp con ese jugador:</b><br>";
  jugadores.forEach(j => {
    const link = waLink(j.telefono, msg.replace("{nombre}", j.nombre || ""));
    if (link) html += "<a href='" + link + "' target='_blank'>" + j.nombre + " (" + j.telefono + ")</a>";
  });
  html += "</div>";
  cont.innerHTML = html;
}

// ---------- DISPATCH DE RESULTADOS Y COBROS POR ROL ----------
function cargarResultados() {
  if (rol === "jugador") return cargarResultadosJugador();
  if (rol === "vendedor") return cargarResultadosVendedor();
  if (rol === "revendedor") return cargarResultadosRevendedor();
}
function cargarCobros() {
  if (rol === "vendedor") return cargarCobrosVendedor();
}
window.ACCIONES = window.ACCIONES || {};
ACCIONES.resultados = cargarResultados;
ACCIONES.cobros = cargarCobros;

// ---------- ARRANQUE ----------
const _params = new URLSearchParams(window.location.search);
const _cod = _params.get("codigo");
if (_cod) {
  document.getElementById("bloque-login").style.display = "none";
  document.getElementById("login-msg").style.display = "none";
  document.getElementById("form-registro").style.display = "block";
  const inputCod = document.getElementById("reg-codigo");
  inputCod.value = _cod;
  inputCod.readOnly = true;
}

if (token) { mostrarPanel(); }
