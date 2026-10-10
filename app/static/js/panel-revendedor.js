// ---------- REVENDEDOR: SORTEOS Y JUGADAS ----------
async function cargarRSorteos() {
  try {
    const ss = await api("/revendedor/sorteos", "GET");
    SORTEOS_ABIERTOS_CACHE["r-sorteo"] = {};
    SORTEOS_ABIERTOS_CACHE["r-cupo-sorteo"] = {};
    ss.forEach(s => { SORTEOS_ABIERTOS_CACHE["r-sorteo"][s.id] = s; SORTEOS_ABIERTOS_CACHE["r-cupo-sorteo"][s.id] = s; });
    let html = "<table><tr><th>#</th><th>Img</th><th>Sorteo</th><th>Horario</th><th>Dia</th><th>Cierre</th><th>Estado</th><th>Precio</th><th>Pozo / Premio</th></tr>";
    ss.forEach(s => {
      const celdaPozo = tienePremioNombre(s) ? "<b style='color:#22c55e'>" + s.premio_nombre + "</b>" : "<b style='color:#22c55e'>$" + s.pozo + "</b>";
      html += "<tr><td>" + s.id + "</td><td>" + (s.imagen_url ? "<img src='" + s.imagen_url + "' style='width:40px;height:40px;object-fit:cover;border-radius:4px'>" : "-") + "</td><td><b>" + nombreSorteo(s) + "</b>" + (s.titulo ? "<div class='chico'>" + s.modalidad + "</div>" : "") + (s.reprogramando ? " (REPROGRAMANDO)" : "") + "<div class='chico'>" + (s.detalle || "") + "</div></td><td>" + s.horario + "</td><td>" + fmtFecha(s.fecha) + "</td><td>" + (s.hora_cierre || "sin limite") + "</td><td>" + s.estado + "</td><td>$" + s.precio_jugada + "</td><td>" + celdaPozo + "</td></tr>";
    });
    document.getElementById("lista-rsorteos").innerHTML = html + "</table>";
  } catch (e) { aviso(e.message, true); }
}

async function rCargarJugada() {
  const selJugador = document.getElementById("r-jugador-select").value;
  const cuerpo = {
    sorteo_id: parseInt(document.getElementById("r-sorteo").value),
    numeros: parseNumeros(document.getElementById("r-numeros").value),
  };
  if (selJugador) cuerpo.jugador_id = parseInt(selJugador);
  else cuerpo.jugador_nombre = document.getElementById("r-jugador").value || null;
  try {
    const d = await api("/revendedor/jugadas", "POST", cuerpo);
    let txt = "Jugada #" + d.id + " cargada y APROBADA (venta directa).";
    if (d.aviso_iguales && d.aviso_iguales.aplica && d.aviso_iguales.coincidencias > 0) {
      txt += " Atencion: hay " + d.aviso_iguales.coincidencias + " jugada(s) igual(es) en el sorteo; si gana, el pozo se divide y el premio estimado es $" + d.aviso_iguales.premio_estimado + ".";
    }
    aviso(txt);
    document.getElementById("r-numeros").value = "";
  }
  catch (e) { aviso(e.message, true); }
}

// ---------- REVENDEDOR: VENTA DE CUPOS ----------
function llenarSelectJugadorCupoR() {
  const sel = document.getElementById("r-cupo-jugador");
  if (!sel) return;
  const todos = RJUG_CACHE ? Object.values(RJUG_CACHE) : [];
  const idSel = document.getElementById("r-cupo-sorteo").value;
  const s = SORTEOS_ABIERTOS_CACHE["r-cupo-sorteo"] && SORTEOS_ABIERTOS_CACHE["r-cupo-sorteo"][idSel];
  let lista = todos.filter(j => j.activo);
  if (s && s.solo_participantes && s.participantes && s.participantes.length) {
    lista = lista.filter(j => s.participantes.includes(j.nombre));
  }
  sel.innerHTML = "<option value=''>Elegi jugador...</option>" + lista.map(j => "<option value='" + j.id + "'>" + j.nombre + " (" + j.usuario + ")</option>").join("");
}

function updateCupoResumenR() {
  const caja = document.getElementById("r-cupo-resumen");
  if (!caja) return;
  const idSel = document.getElementById("r-cupo-sorteo").value;
  const s = SORTEOS_ABIERTOS_CACHE["r-cupo-sorteo"] && SORTEOS_ABIERTOS_CACHE["r-cupo-sorteo"][idSel];
  const cant = parseInt(document.getElementById("r-cupo-cantidad").value || "0", 10);
  if (!s || !cant || cant < 1) { caja.textContent = ""; return; }
  const total = Math.round((s.precio_jugada || 0) * cant * 100) / 100;
  caja.innerHTML = "<b>Total a cobrarle al jugador: $" + total + "</b> (" + cant + " x $" + s.precio_jugada + "). Al confirmar, ese monto se reparte y suma al pozo en el acto.";
}

async function venderCuposR() {
  const sorteoId = document.getElementById("r-cupo-sorteo").value;
  const jugadorId = document.getElementById("r-cupo-jugador").value;
  const cant = parseInt(document.getElementById("r-cupo-cantidad").value || "0", 10);
  const msgBox = document.getElementById("r-cupo-msg");
  if (!sorteoId || !jugadorId || !cant || cant < 1) { aviso("Completa sorteo, jugador y cantidad", true); return; }
  const s = SORTEOS_ABIERTOS_CACHE["r-cupo-sorteo"][sorteoId];
  const j = (RJUG_CACHE || {})[jugadorId] || (Object.values(RJUG_CACHE || {}).find(x => String(x.id) === String(jugadorId)));
  const total = Math.round((s.precio_jugada || 0) * cant * 100) / 100;
  if (!confirm("Vas a vender " + cant + " jugada(s) del sorteo #" + sorteoId + " a " + (j ? j.nombre : jugadorId) + " por $" + total + ". El jugador debe haberte pagado ese monto fuera del sistema. Continuar?")) return;
  if (!confirm("CONFIRMACION FINAL: esta venta no se puede editar ni cancelar despues. El monto suma al pozo y a tu comision ahora mismo. Confirmas?")) return;
  try {
    const d = await api("/revendedor/cupos", "POST", { sorteo_id: parseInt(sorteoId), jugador_id: parseInt(jugadorId), cantidad: cant });
    if (msgBox) { msgBox.style.display = "block"; msgBox.className = "mensaje ok"; msgBox.textContent = "Vendiste " + d.cantidad + " jugada(s) por $" + d.monto_total + ". El jugador ya las ve disponibles en su panel."; }
    document.getElementById("r-cupo-cantidad").value = 1;
    updateCupoResumenR();
  } catch (e) {
    if (msgBox) { msgBox.style.display = "block"; msgBox.className = "mensaje error"; msgBox.textContent = e.message; }
  }
}

async function cargarRJugadas() {
  try {
    const js = await api("/revendedor/jugadas", "GET");
    let html = "<table><tr><th>#</th><th>Sorteo</th><th>Numeros</th><th>Precio</th><th>Estado</th><th>Premio</th><th>Tu comision</th></tr>";
    js.forEach(j => { html += "<tr><td>" + j.id + "</td><td>" + j.sorteo_id + "</td><td>" + j.numeros + "</td><td>$" + j.precio + "</td><td>" + j.estado + "</td><td>$" + (j.premio ?? "-") + "</td><td>$" + (j.mi_comision ?? "-") + "</td></tr>"; });
    document.getElementById("lista-rjugadas").innerHTML = html + "</table>";
  } catch (e) { aviso(e.message, true); }
}

async function cargarRResumen() {
  try {
    const r = await api("/revendedor/resumen", "GET");
    document.getElementById("caja-rresumen").innerHTML = "<table><tr><th>Jugadas aprobadas</th><th>Vendido</th><th>Tu comision</th></tr><tr><td>" + r.jugadas_aprobadas + "</td><td>$" + r.vendido + "</td><td>$" + r.mi_comision + "</td></tr></table>";
  } catch (e) { aviso(e.message, true); }
}

// ---------- REVENDEDOR: JUGADORES ----------
async function crearRJugador() {
  const cuerpo = {
    usuario: document.getElementById("rj-usuario").value,
    password: document.getElementById("rj-password").value,
    nombre: document.getElementById("rj-nombre").value,
    telefono: document.getElementById("rj-telefono").value,
    datos_cobro: document.getElementById("rj-cobro").value,
    cobro_transferencia: document.getElementById("rj-transferencia").checked,
  };
  try { await api("/revendedor/jugadores", "POST", cuerpo); aviso("Jugador cargado a tu linea"); cargarRJugadores(); }
  catch (e) { aviso(e.message, true); }
}

async function cargarRJugadores() {
  cargarLinkRevendedor();
  try {
    const js = await api("/revendedor/jugadores", "GET");
    RJUG_CACHE = {};
    js.forEach(j => { RJUG_CACHE[j.id] = j; });
    let html = "<table><tr><th>#</th><th>Usuario</th><th>Nombre</th><th>Telefono</th><th>Alias/CBU</th><th>Transf.</th><th>Activo</th><th>Acciones</th></tr>";
    js.forEach(j => {
      const link = waLink(j.telefono, "Hola " + (j.nombre || "") + ", te escribo de RIFALO.");
      const waBtn = link ? "<a class='wa' href='" + link + "' target='_blank' style='display:inline-block;padding:4px 8px;border-radius:4px;background:#25D366;color:#fff;text-decoration:none;font-size:11px'>WhatsApp</a>" : "";
      html += "<tr><td>" + j.id + "</td><td>" + j.usuario + "</td><td>" + j.nombre + "</td><td>" + (j.telefono || "-") + "</td><td>" + (j.datos_cobro || "-") + "</td><td>" + (j.cobro_transferencia ? "si" : "no") + "</td><td>" + (j.activo ? "si" : "no") + "</td><td><button class='secundario' onclick='empezarEdicionRJugador(" + j.id + ")'>Editar</button><button class='peligro' onclick='eliminarRJugador(" + j.id + ")'>Eliminar</button> " + waBtn + "</td></tr>";
    });
    document.getElementById("lista-rjugadores").innerHTML = html + "</table>";
    const wl = document.getElementById("rjugadores-wa-links");
    if (wl) wl.innerHTML = "";
  } catch (e) { aviso(e.message, true); }
}

function empezarEdicionRJugador(id) {
  const j = RJUG_CACHE[id];
  if (!j) return;
  rjug_edit_id = id;
  const bar = document.getElementById("rjug-edit-bar");
  bar.style.display = "block";
  bar.innerHTML =
    "Editando jugador " + j.usuario + "." +
    "<div class='grilla'>" +
    "<div><label>Nombre y apellido</label><input id='rje-nombre'></div>" +
    "<div><label>Telefono</label><input id='rje-telefono'></div>" +
    "<div><label>Alias o CBU</label><input id='rje-cobro'></div>" +
    "<div><label>Nueva contrasenia (vacio = no cambiar)</label><input id='rje-password' type='password'></div>" +
    "</div>" +
    "<div class='check-linea'><input type='checkbox' id='rje-transferencia'><span>Cobra por transferencia</span></div>" +
    "<div class='check-linea'><input type='checkbox' id='rje-activo'><span>Jugador activo</span></div>" +
    "<button onclick='guardarEdicionRJugador()'>Guardar cambios</button><button class='peligro' onclick='cancelarEdicionRJugador()'>Cancelar</button>";
  document.getElementById("rje-nombre").value = j.nombre || "";
  document.getElementById("rje-telefono").value = j.telefono || "";
  document.getElementById("rje-cobro").value = j.datos_cobro || "";
  document.getElementById("rje-password").value = "";
  document.getElementById("rje-transferencia").checked = Boolean(j.cobro_transferencia);
  document.getElementById("rje-activo").checked = Boolean(j.activo);
  bar.scrollIntoView({ behavior: "smooth" });
}

function cancelarEdicionRJugador() {
  rjug_edit_id = null;
  document.getElementById("rjug-edit-bar").style.display = "none";
}

async function guardarEdicionRJugador() {
  const cuerpo = {
    nombre: document.getElementById("rje-nombre").value,
    telefono: document.getElementById("rje-telefono").value || null,
    datos_cobro: document.getElementById("rje-cobro").value,
    cobro_transferencia: document.getElementById("rje-transferencia").checked,
    activo: document.getElementById("rje-activo").checked,
  };
  const pass = document.getElementById("rje-password").value;
  if (pass) cuerpo.password = pass;
  try {
    await api("/revendedor/jugadores/" + rjug_edit_id, "PUT", cuerpo);
    aviso("Jugador actualizado");
    cancelarEdicionRJugador();
    cargarRJugadores();
  } catch (e) { aviso(e.message, true); }
}

async function eliminarRJugador(id) {
  if (!confirm("Eliminar el jugador? Solo se puede si todavia no tiene jugadas.")) return;
  try { await api("/revendedor/jugadores/" + id, "DELETE"); aviso("Jugador eliminado"); cargarRJugadores(); }
  catch (e) { aviso(e.message, true); }
}

// ---------- REVENDEDOR: RESULTADOS Y PREMIOS A ENTREGAR ----------
async function cargarResultadosRevendedor() {
  const caja = document.getElementById("lista-resultados-revendedor");
  if (!caja) return;
  try {
    const rs = await api("/revendedor/resultados", "GET");
    if (!rs.length) { caja.innerHTML = "<p class='chico'>Todavia no hay sorteos liquidados.</p>"; return; }
    let html = "";
    rs.forEach(r => {
      html += "<div class='buscador-box'>";
      html += "<b>Sorteo #" + r.sorteo_id + "</b> - " + (r.titulo || r.modalidad) + " " + r.horario + " - " + fmtFecha(r.fecha) + "<br>";
      html += resultadosColumnaHTML(r.resultados);
      html += "<span class='chico'>Cantidad de ganadores: " + r.cantidad_ganadores + "</span><br>";
      if (r.mis_ganadores && r.mis_ganadores.length) {
        r.mis_ganadores.forEach(g => {
          const premioTxt = r.premio_nombre ? ("GANO: " + r.premio_nombre) : ("GANO $" + g.premio);
          html += "<div class='cobro-box'><b>Tu jugador " + g.jugador_nombre + " " + premioTxt + "</b> (jugada #" + g.jugada_id + ").<br>";
          html += (g.premio_pagado ? "El vendedor marco el premio como entregado. " : "<b>Pendiente de entrega.</b> ");
          html += (g.premio_cobrado ? "<b>El jugador confirmo que cobro ✔</b>" : "El jugador aun no confirmo el cobro.");
          html += "<br><span class='chico'>Comunicate con tu jugador asi le entregas su premio.</span></div>";
        });
      } else if (r.tuve_jugadores) {
        html += "<div class='chico'>No tenes jugadores ganadores en este sorteo.</div>";
      } else {
        html += "<div class='chico'>Sin jugadores tuyos en este sorteo.</div>";
      }
      html += "</div>";
    });
    caja.innerHTML = html;
  } catch (e) { aviso(e.message, true); }
}

// ---------- REGISTRO DE PESTANAS DEL REVENDEDOR ----------
window.ACCIONES = window.ACCIONES || {};
ACCIONES.rsorteos = async () => { await cargarRSorteos(); await cargarMisCuposPagos(); };
ACCIONES.rcupos = async () => {
  await llenarSelectSorteos("/revendedor/sorteos", "r-cupo-sorteo");
  await cargarSelectJugadores("r");
  llenarSelectJugadorCupoR();
  updateCupoResumenR();
};
ACCIONES.rcargar = () => { llenarSelectSorteos("/revendedor/sorteos", "r-sorteo"); cargarSelectJugadores("r"); };
ACCIONES.rjugadas = cargarRJugadas;
ACCIONES.rresumen = cargarRResumen;
ACCIONES.rjugadores = cargarRJugadores;
ACCIONES.resultados = cargarResultados;

// ---------- REVENDEDOR: MIS CUPOS Y MIS PAGOS ----------
async function cargarMisCuposPagos() {
  const cajaCupos = document.getElementById("r-mis-cupos");
  const cajaPagos = document.getElementById("r-mis-pagos");
  if (cajaCupos) {
    try {
      const cupos = await api("/revendedor/mis-cupos", "GET");
      let html = "<h3>Mis cupos de venta por sorteo</h3>";
      if (!cupos.length) html += "<p class='chico'>Tu vendedor aun no te asigno cupos propios. Podes vender (descuenta del cupo de tu vendedor).</p>";
      else {
        html += "<table><tr><th>Sorteo</th><th>Cupo</th><th>Usado</th><th>Disponibles</th></tr>";
        cupos.forEach(c => { html += "<tr><td>#" + c.sorteo_id + " " + c.sorteo_titulo + "</td><td>" + c.cupo_total + "</td><td>" + c.cupo_usado + "</td><td><b style='color:" + (c.disponibles > 0 ? "#22c55e" : "#ef4444") + "'>" + c.disponibles + "</b></td></tr>"; });
        html += "</table>";
      }
      cajaCupos.innerHTML = html;
    } catch (e) { cajaCupos.innerHTML = ""; }
  }
  if (cajaPagos) {
    try {
      const pagos = await api("/revendedor/mis-pagos", "GET");
      let html = "<h3>Pagos que tu vendedor te confirmo</h3>";
      if (!pagos.length) html += "<p class='chico'>Sin pagos registrados todavia.</p>";
      else {
        html += "<table><tr><th>Fecha</th><th>Sorteo</th><th>Jugadas pagadas</th><th>Monto</th></tr>";
        pagos.forEach(p => { html += "<tr><td>" + fmtFecha(p.creado_en) + "</td><td>#" + p.sorteo_id + " " + p.sorteo_titulo + "</td><td>" + p.cantidad_jugadas + "</td><td>$" + p.monto + "</td></tr>"; });
        html += "</table>";
      }
      cajaPagos.innerHTML = html;
    } catch (e) { cajaPagos.innerHTML = ""; }
  }
}
