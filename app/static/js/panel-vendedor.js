// ---------- VENDEDOR: RESUMEN Y JUGADAS ----------
async function cargarVResumen() {
  try {
    const r = await api("/vendedor/resumen", "GET");
    document.getElementById("caja-vresumen").innerHTML = "<table><tr><th>Jugadas aprobadas</th><th>Vendido</th><th>Tu comision</th><th>Pagado a tus revendedores</th></tr><tr><td>" + r.jugadas_aprobadas + "</td><td>$" + r.vendido + "</td><td>$" + r.mi_comision + "</td><td>$" + r.comision_revendedores + "</td></tr></table>";
  } catch (e) { aviso(e.message, true); }
}

async function vCargarJugada() {
  const selJugador = document.getElementById("v-jugador-select").value;
  const cuerpo = {
    sorteo_id: parseInt(document.getElementById("v-sorteo").value),
    numeros: parseNumeros(document.getElementById("v-numeros").value),
  };
  if (selJugador) cuerpo.jugador_id = parseInt(selJugador);
  else cuerpo.jugador_nombre = document.getElementById("v-jugador").value || null;
  try {
    const d = await api("/vendedor/jugadas", "POST", cuerpo);
    let txt = "Jugada #" + d.id + " cargada y APROBADA (venta directa).";
    if (d.aviso_iguales && d.aviso_iguales.aplica && d.aviso_iguales.coincidencias > 0) {
      txt += " Atencion: hay " + d.aviso_iguales.coincidencias + " jugada(s) igual(es) en el sorteo; si gana, el pozo se divide y el premio estimado es $" + d.aviso_iguales.premio_estimado + ".";
    }
    aviso(txt);
    document.getElementById("v-numeros").value = "";
  }
  catch (e) { aviso(e.message, true); }
}

// ---------- VENDEDOR: VENTA DE CUPOS ----------
function llenarSelectJugadorCupo() {
  const sel = document.getElementById("v-cupo-jugador");
  if (!sel) return;
  const todos = JUGADORES_CACHE["v"] || [];
  const idSel = document.getElementById("v-cupo-sorteo").value;
  const s = SORTEOS_ABIERTOS_CACHE["v-cupo-sorteo"] && SORTEOS_ABIERTOS_CACHE["v-cupo-sorteo"][idSel];
  let lista = todos.filter(j => j.activo);
  if (s && s.solo_participantes && s.participantes && s.participantes.length) {
    lista = lista.filter(j => s.participantes.includes(j.nombre));
  }
  sel.innerHTML = "<option value=''>Elegi jugador...</option>" + lista.map(j => "<option value='" + j.id + "'>" + j.nombre + " (" + j.usuario + ")</option>").join("");
}

function updateCupoResumen() {
  const caja = document.getElementById("v-cupo-resumen");
  if (!caja) return;
  const idSel = document.getElementById("v-cupo-sorteo").value;
  const s = SORTEOS_ABIERTOS_CACHE["v-cupo-sorteo"] && SORTEOS_ABIERTOS_CACHE["v-cupo-sorteo"][idSel];
  const cant = parseInt(document.getElementById("v-cupo-cantidad").value || "0", 10);
  if (!s || !cant || cant < 1) { caja.textContent = ""; return; }
  const total = Math.round((s.precio_jugada || 0) * cant * 100) / 100;
  caja.innerHTML = "<b>Total a cobrarle al jugador: $" + total + "</b> (" + cant + " x $" + s.precio_jugada + "). Al confirmar, ese monto se reparte y suma al pozo en el acto.";
}

async function venderCupos() {
  const sorteoId = document.getElementById("v-cupo-sorteo").value;
  const jugadorId = document.getElementById("v-cupo-jugador").value;
  const cant = parseInt(document.getElementById("v-cupo-cantidad").value || "0", 10);
  const msgBox = document.getElementById("v-cupo-msg");
  if (!sorteoId || !jugadorId || !cant || cant < 1) { aviso("Completa sorteo, jugador y cantidad", true); return; }
  const s = SORTEOS_ABIERTOS_CACHE["v-cupo-sorteo"][sorteoId];
  const j = (JUGADORES_CACHE["v"] || []).find(x => String(x.id) === String(jugadorId));
  const total = Math.round((s.precio_jugada || 0) * cant * 100) / 100;
  if (!confirm("Vas a vender " + cant + " jugada(s) del sorteo #" + sorteoId + " a " + (j ? j.nombre : jugadorId) + " por $" + total + ". El jugador debe haberte pagado ese monto fuera del sistema. Continuar?")) return;
  if (!confirm("CONFIRMACION FINAL: esta venta no se puede editar ni cancelar despues. El monto suma al pozo y a tu comision ahora mismo. Confirmas?")) return;
  try {
    const d = await api("/vendedor/cupos", "POST", { sorteo_id: parseInt(sorteoId), jugador_id: parseInt(jugadorId), cantidad: cant });
    if (msgBox) { msgBox.style.display = "block"; msgBox.className = "mensaje ok"; msgBox.textContent = "Vendiste " + d.cantidad + " jugada(s) por $" + d.monto_total + ". El jugador ya las ve disponibles en su panel."; }
    document.getElementById("v-cupo-cantidad").value = 1;
    updateCupoResumen();
  } catch (e) {
    if (msgBox) { msgBox.style.display = "block"; msgBox.className = "mensaje error"; msgBox.textContent = e.message; }
  }
}

async function cargarVPendientes() {
  try {
    const js = await api("/vendedor/jugadas/pendientes", "GET");
    if (!js.length) { document.getElementById("lista-vpendientes").innerHTML = "<p class='chico'>Nada pendiente.</p>"; return; }
    let html = "<table><tr><th>#</th><th>Sorteo</th><th>Numeros</th><th>Precio</th><th>Jugador</th><th>Origen</th><th>Acciones</th></tr>";
    js.forEach(j => {
      html += "<tr><td>" + j.id + "</td><td>" + j.sorteo_id + "</td><td>" + j.numeros + "</td><td>$" + j.precio + "</td><td>" + (j.jugador_nombre || "-") + "</td><td>" + (j.revendedor_id ? "revendedor #" + j.revendedor_id : (j.jugador_id ? "jugador #" + j.jugador_id : "propia")) + "</td><td><button onclick='aprobarV(" + j.id + ")'>Aprobar</button><button class='peligro' onclick='rechazarV(" + j.id + ")'>Rechazar</button></td></tr>";
    });
    document.getElementById("lista-vpendientes").innerHTML = html + "</table>";
  } catch (e) { aviso(e.message, true); }
}

async function aprobarV(id) {
  try { await api("/vendedor/jugadas/" + id + "/aprobar", "POST"); aviso("Jugada aprobada"); cargarVPendientes(); }
  catch (e) { aviso(e.message, true); }
}

async function rechazarV(id) {
  try { await api("/vendedor/jugadas/" + id + "/rechazar", "POST"); aviso("Jugada rechazada"); cargarVPendientes(); }
  catch (e) { aviso(e.message, true); }
}

async function cargarVJugadas() {
  try {
    const js = await api("/vendedor/jugadas", "GET");
    let html = "<table><tr><th>#</th><th>Sorteo</th><th>Numeros</th><th>Precio</th><th>Estado</th><th>Premio</th><th>Tu comision</th></tr>";
    js.forEach(j => { html += "<tr><td>" + j.id + "</td><td>" + j.sorteo_id + "</td><td>" + j.numeros + "</td><td>$" + j.precio + "</td><td>" + j.estado + "</td><td>$" + (j.premio ?? "-") + "</td><td>$" + (j.mi_comision ?? "-") + "</td></tr>"; });
    document.getElementById("lista-vjugadas").innerHTML = html + "</table>";
  } catch (e) { aviso(e.message, true); }
}

// ---------- VENDEDOR: REVENDEDORES ----------
async function crearVRevendedor() {
  const cuerpo = {
    usuario: document.getElementById("vrev-usuario").value,
    password: document.getElementById("vrev-password").value,
    nombre: document.getElementById("vrev-nombre").value,
    telefono: document.getElementById("vrev-telefono").value || null,
    codigo: document.getElementById("vrev-codigo").value,
    comision_pct: parseFloat(document.getElementById("vrev-comision").value),
  };
  try { await api("/vendedor/revendedores", "POST", cuerpo); aviso("Revendedor creado"); cargarVRevendedores(); }
  catch (e) { aviso(e.message, true); }
}

async function cargarVRevendedores() {
  try {
    const rs = await api("/vendedor/revendedores", "GET");
    REV_CACHE = {};
    rs.forEach(r => { REV_CACHE[r.id] = r; });
    let html = "<table><tr><th>#</th><th>Usuario</th><th>Nombre</th><th>Codigo</th><th>Comision</th><th>Activo</th><th>Acciones</th></tr>";
    rs.forEach(r => {
      html += "<tr><td>" + r.id + "</td><td>" + r.usuario + "</td><td>" + r.nombre + "</td><td>" + r.codigo + "</td><td>" + r.comision_pct + "%</td><td>" + (r.activo ? "si" : "no") + "</td><td><button class='secundario' onclick='empezarEdicionVRev(" + r.id + ")'>Editar</button><button class='peligro' onclick='eliminarVRev(" + r.id + ")'>Eliminar</button></td></tr>";
    });
    document.getElementById("lista-vrevendedores").innerHTML = html + "</table>";
  } catch (e) { aviso(e.message, true); }
}

function empezarEdicionVRev(id) {
  const r = REV_CACHE[id];
  if (!r) return;
  rev_edit_id = id;
  const bar = document.getElementById("vrev-edit-bar");
  bar.style.display = "block";
  bar.innerHTML =
    "Editando revendedor " + r.usuario + "." +
    "<div class='grilla'>" +
    "<div><label>Nombre</label><input id='vre-nombre'></div>" +
    "<div><label>Telefono</label><input id='vre-telefono'></div>" +
    "<div><label>Codigo</label><input id='vre-codigo'></div>" +
    "<div><label>Comision % (menor o igual a la tuya)</label><input id='vre-comision' type='number'></div>" +
    "<div><label>Nueva contrasenia (vacio = no cambiar)</label><input id='vre-password' type='password'></div>" +
    "</div>" +
    "<div class='check-linea'><input type='checkbox' id='vre-activo'><span>Revendedor activo</span></div>" +
    "<button onclick='guardarEdicionVRev()'>Guardar cambios</button><button class='peligro' onclick='cancelarEdicionVRev()'>Cancelar</button>";
  document.getElementById("vre-nombre").value = r.nombre || "";
  document.getElementById("vre-telefono").value = r.telefono || "";
  document.getElementById("vre-codigo").value = r.codigo || "";
  document.getElementById("vre-comision").value = r.comision_pct;
  document.getElementById("vre-password").value = "";
  document.getElementById("vre-activo").checked = Boolean(r.activo);
  bar.scrollIntoView({ behavior: "smooth" });
}

function cancelarEdicionVRev() {
  rev_edit_id = null;
  document.getElementById("vrev-edit-bar").style.display = "none";
}

async function guardarEdicionVRev() {
  const cuerpo = {
    nombre: document.getElementById("vre-nombre").value,
    telefono: document.getElementById("vre-telefono").value || null,
    codigo: document.getElementById("vre-codigo").value,
    comision_pct: parseFloat(document.getElementById("vre-comision").value),
    activo: document.getElementById("vre-activo").checked,
  };
  const pass = document.getElementById("vre-password").value;
  if (pass) cuerpo.password = pass;
  try {
    await api("/vendedor/revendedores/" + rev_edit_id, "PUT", cuerpo);
    aviso("Revendedor actualizado");
    cancelarEdicionVRev();
    cargarVRevendedores();
  } catch (e) { aviso(e.message, true); }
}

async function eliminarVRev(id) {
  if (!confirm("Eliminar el revendedor? Solo se puede si no tiene jugadores ni jugadas.")) return;
  try { await api("/vendedor/revendedores/" + id, "DELETE"); aviso("Revendedor eliminado"); cargarVRevendedores(); }
  catch (e) { aviso(e.message, true); }
}

// ---------- VENDEDOR: JUGADORES ----------
async function crearVJugador() {
  const cuerpo = {
    usuario: document.getElementById("vj-usuario").value,
    password: document.getElementById("vj-password").value,
    nombre: document.getElementById("vj-nombre").value,
    telefono: document.getElementById("vj-telefono").value,
    datos_cobro: document.getElementById("vj-cobro").value,
    cobro_transferencia: document.getElementById("vj-transferencia").checked,
  };
  try { await api("/vendedor/jugadores", "POST", cuerpo); aviso("Jugador cargado a tu linea"); cargarVJugadores(); }
  catch (e) { aviso(e.message, true); }
}

async function cargarVJugadores() {
  cargarLinkVendedor();
  try {
    const js = await api("/vendedor/jugadores", "GET");
    VJUG_CACHE = {};
    js.forEach(j => { VJUG_CACHE[j.id] = j; });
    let html = "<table><tr><th>#</th><th>Usuario</th><th>Nombre</th><th>Telefono</th><th>Alias/CBU</th><th>Transf.</th><th>Via</th><th>Activo</th><th>Acciones</th></tr>";
    js.forEach(j => {
      const link = waLink(j.telefono, "Hola " + (j.nombre || "") + ", te escribo de RIFALO.");
      const waBtn = link ? "<a class='wa' href='" + link + "' target='_blank' style='display:inline-block;padding:4px 8px;border-radius:4px;background:#25D366;color:#fff;text-decoration:none;font-size:11px'>WhatsApp</a>" : "";
      html += "<tr><td>" + j.id + "</td><td>" + j.usuario + "</td><td>" + j.nombre + "</td><td>" + (j.telefono || "-") + "</td><td>" + (j.datos_cobro || "-") + "</td><td>" + (j.cobro_transferencia ? "si" : "no") + "</td><td>" + (j.revendedor || "directo") + "</td><td>" + (j.activo ? "si" : "no") + "</td><td><button class='secundario' onclick='empezarEdicionVJugador(" + j.id + ")'>Editar</button><button class='peligro' onclick='eliminarVJugador(" + j.id + ")'>Eliminar</button> " + waBtn + "</td></tr>";
    });
    document.getElementById("lista-vjugadores").innerHTML = html + "</table>";
    const wl = document.getElementById("vjugadores-wa-links");
    if (wl) wl.innerHTML = "";
  } catch (e) { aviso(e.message, true); }
}

function empezarEdicionVJugador(id) {
  const j = VJUG_CACHE[id];
  if (!j) return;
  vjug_edit_id = id;
  const bar = document.getElementById("vjug-edit-bar");
  bar.style.display = "block";
  bar.innerHTML =
    "Editando jugador " + j.usuario + "." +
    "<div class='grilla'>" +
    "<div><label>Nombre y apellido</label><input id='vje-nombre'></div>" +
    "<div><label>Telefono</label><input id='vje-telefono'></div>" +
    "<div><label>Alias o CBU</label><input id='vje-cobro'></div>" +
    "<div><label>Nueva contrasenia (vacio = no cambiar)</label><input id='vje-password' type='password'></div>" +
    "</div>" +
    "<div class='check-linea'><input type='checkbox' id='vje-transferencia'><span>Cobra por transferencia</span></div>" +
    "<div class='check-linea'><input type='checkbox' id='vje-activo'><span>Jugador activo</span></div>" +
    "<button onclick='guardarEdicionVJugador()'>Guardar cambios</button><button class='peligro' onclick='cancelarEdicionVJugador()'>Cancelar</button>";
  document.getElementById("vje-nombre").value = j.nombre || "";
  document.getElementById("vje-telefono").value = j.telefono || "";
  document.getElementById("vje-cobro").value = j.datos_cobro || "";
  document.getElementById("vje-password").value = "";
  document.getElementById("vje-transferencia").checked = Boolean(j.cobro_transferencia);
  document.getElementById("vje-activo").checked = Boolean(j.activo);
  bar.scrollIntoView({ behavior: "smooth" });
}

function cancelarEdicionVJugador() {
  vjug_edit_id = null;
  document.getElementById("vjug-edit-bar").style.display = "none";
}

async function guardarEdicionVJugador() {
  const cuerpo = {
    nombre: document.getElementById("vje-nombre").value,
    telefono: document.getElementById("vje-telefono").value || null,
    datos_cobro: document.getElementById("vje-cobro").value,
    cobro_transferencia: document.getElementById("vje-transferencia").checked,
    activo: document.getElementById("vje-activo").checked,
  };
  const pass = document.getElementById("vje-password").value;
  if (pass) cuerpo.password = pass;
  try {
    await api("/vendedor/jugadores/" + vjug_edit_id, "PUT", cuerpo);
    aviso("Jugador actualizado");
    cancelarEdicionVJugador();
    cargarVJugadores();
  } catch (e) { aviso(e.message, true); }
}

async function eliminarVJugador(id) {
  if (!confirm("Eliminar el jugador? Solo se puede si todavia no tiene jugadas.")) return;
  try { await api("/vendedor/jugadores/" + id, "DELETE"); aviso("Jugador eliminado"); cargarVJugadores(); }
  catch (e) { aviso(e.message, true); }
}

// ---------- VENDEDOR: RESULTADOS Y PREMIOS A ENTREGAR ----------
async function cargarResultadosVendedor() {
  const caja = document.getElementById("lista-resultados-vendedor");
  if (!caja) return;
  try {
    const rs = await api("/vendedor/resultados", "GET");
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
          if (g.premio_pagado) {
            html += "<b style='color:#22c55e'>Entregado por vos ✔</b> <button class='secundario' onclick='marcarPremioVendedor(" + g.jugada_id + ", false)'>Desmarcar entrega</button><br>";
          } else {
            html += "<b style='color:#f59e0b'>Pendiente de entrega.</b> <button onclick='marcarPremioVendedor(" + g.jugada_id + ", true)'>Marcar como entregado</button><br>";
          }
          if (g.premio_cobrado) {
            html += "<b style='color:#22c55e'>Tu jugador confirmo que cobro ✔</b>";
          } else {
            html += "<span class='chico'>Tu jugador aun no confirmo el cobro.</span>";
          }
          html += "</div>";
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

async function marcarPremioVendedor(jugadaId, pagado) {
  const msg = pagado ? "Confirmas que entregaste el premio al jugador?" : "Vas a desmarcar la entrega. El jugador volvera a ver 'pendiente'. Continuar?";
  if (!confirm(msg)) return;
  try {
    await api("/vendedor/jugadas/" + jugadaId + "/marcar-premio", "POST", { pagado: pagado });
    aviso(pagado ? "Marcaste el premio como entregado." : "Desmarcaste la entrega.");
    cargarResultadosVendedor();
  } catch (e) { aviso(e.message, true); }
}

// ---------- VENDEDOR: MIS COBROS (liquidaciones de comisiones) ----------
async function cargarCobrosVendedor() {
  const caja = document.getElementById("lista-cobros-vendedor");
  if (!caja) return;
  try {
    const ls = await api("/vendedor/cobros", "GET");
    if (!ls.length) { caja.innerHTML = "<p class='chico'>Todavia no hay liquidaciones. El administrador genera la liquidacion de tus comisiones por periodo.</p>"; return; }
    let html = "";
    ls.forEach(l => {
      let estado;
      if (l.pagado_admin && l.cobrado_vendedor) estado = "<span class='ok'>Pagado y confirmado ✔</span>";
      else if (l.pagado_admin) estado = "<span class='warn'>El admin marco el pago. Confirma que cobraste.</span>";
      else estado = "<span class='chico'>Pendiente de pago por el admin.</span>";
      html += "<div class='buscador-box'>";
      html += "<b>Liquidacion #" + l.id + "</b> · Periodo " + fmtFecha(l.desde) + " a " + fmtFecha(l.hasta) + "<br>";
      html += "<span style='font-size:20px;font-weight:bold;color:#22c55e'>$" + l.monto + "</span> " + estado + "<br>";
      if (l.pagado_en) html += "<span class='chico'>Pagado el " + l.pagado_en.slice(0,10) + "</span><br>";
      if (l.cobrado_en) html += "<span class='chico'>Cobrado el " + l.cobrado_en.slice(0,10) + "</span><br>";
      if (l.detalle && l.detalle.length) {
        html += "<details style='margin-top:6px'><summary class='chico' style='cursor:pointer'>Ver detalle por sorteo (" + l.detalle.length + ")</summary>";
        html += "<table><tr><th>Sorteo</th><th>Modalidad</th><th>Horario</th><th>Dia</th><th>Jugadas</th><th>Vendido</th><th>Comision</th></tr>";
        l.detalle.forEach(d => {
          html += "<tr><td>#" + d.sorteo_id + "</td><td>" + d.modalidad + "</td><td>" + d.horario + "</td><td>" + fmtFecha(d.fecha) + "</td><td>" + d.jugadas + "</td><td>$" + d.vendido + "</td><td>$" + d.comision + "</td></tr>";
        });
        html += "</table></details>";
      }
      if (l.pagado_admin && !l.cobrado_vendedor) {
        html += "<button onclick='confirmarCobroVendedor(" + l.id + ")'>Confirmar que cobre</button>";
      }
      html += "</div>";
    });
    caja.innerHTML = html;
  } catch (e) { aviso(e.message, true); }
}

async function confirmarCobroVendedor(id) {
  if (!confirm("Confirmas que ya cobraste esta liquidacion?")) return;
  try {
    await api("/vendedor/cobros/" + id + "/confirmar-cobro", "POST");
    aviso("Listo, confirmaste el cobro. El administrador ya lo ve.");
    cargarCobrosVendedor();
  } catch (e) { aviso(e.message, true); }
}

// ---------- REGISTRO DE PESTANAS DEL VENDEDOR ----------
window.ACCIONES = window.ACCIONES || {};
ACCIONES.vresumen = cargarVResumen;
ACCIONES.vcupos = async () => {
  await llenarSelectSorteos("/vendedor/sorteos", "v-cupo-sorteo");
  await cargarSelectJugadores("v");
  llenarSelectJugadorCupo();
  updateCupoResumen();
};
ACCIONES.vcargar = () => { llenarSelectSorteos("/vendedor/sorteos", "v-sorteo"); cargarSelectJugadores("v"); };
ACCIONES.vpendientes = cargarVPendientes;
ACCIONES.vjugadas = cargarVJugadas;
ACCIONES.vrevendedores = async () => { await cargarVRevendedores(); llenarSelectRevGestion(); };
ACCIONES.vjugadores = cargarVJugadores;
ACCIONES.resultados = cargarResultados;
ACCIONES.cobros = cargarCobros;

// ---------- VENDEDOR: GESTION DE CUPOS Y PAGOS DE REVENDEDORES ----------
function llenarSelectRevGestion() {
  const sel = document.getElementById("vrev-gestion-select");
  if (!sel) return;
  const revs = Object.values(REV_CACHE || {});
  sel.innerHTML = "<option value=''>Elegi revendedor...</option>" + revs.map(r => "<option value='" + r.id + "'>" + r.nombre + " (" + r.usuario + ")</option>").join("");
  const caja = document.getElementById("vrev-gestion-caja");
  if (caja) caja.innerHTML = "";
}

async function cargarGestionRev() {
  const revId = document.getElementById("vrev-gestion-select").value;
  const caja = document.getElementById("vrev-gestion-caja");
  if (!caja) return;
  if (!revId) { caja.innerHTML = ""; return; }
  try {
    const cupos = await api("/vendedor/revendedores/" + revId + "/cupos", "GET");
    const sorteos = await api("/vendedor/sorteos", "GET");
    let html = "<h3>Cupos del revendedor por sorteo</h3>";
    if (!cupos.length) html += "<p class='chico'>Aun no le asignaste cupos propios. Puede vender sin limite propio (descuenta de tu cupo).</p>";
    else {
      html += "<table><tr><th>Sorteo</th><th>Cupo</th><th>Usado</th><th>Disponibles</th></tr>";
      cupos.forEach(c => { html += "<tr><td>#" + c.sorteo_id + " " + c.sorteo_titulo + "</td><td>" + c.cupo_total + "</td><td>" + c.cupo_usado + "</td><td><b style='color:" + (c.disponibles > 0 ? "#22c55e" : "#ef4444") + "'>" + c.disponibles + "</b></td></tr>"; });
      html += "</table>";
    }
    html += "<h3 style='margin-top:12px'>Ceder mas cupos (se descuentan de TU cupo)</h3>";
    html += "<select id='vrev-gestion-sorteo'>" + sorteos.map(s => "<option value='" + s.id + "'>#" + s.id + " " + (s.titulo || s.modalidad) + "</option>").join("") + "</select>";
    html += "<input id='vrev-gestion-cant' type='number' min='1' value='1' style='width:80px'>";
    html += "<button onclick='asignarCupoRev(" + revId + ")'>Ceder cupos</button>";
    html += "<h3 style='margin-top:12px'>Confirmar pago del revendedor</h3>";
    html += "<select id='vrev-pago-sorteo'>" + sorteos.map(s => "<option value='" + s.id + "'>#" + s.id + " " + (s.titulo || s.modalidad) + "</option>").join("") + "</select>";
    html += "<input id='vrev-pago-cant' type='number' min='1' value='1' style='width:80px'>";
    html += "<button onclick='registrarPagoRev(" + revId + ")'>Confirmar pago</button>";
    html += "<h3 style='margin-top:12px'>Historial de pagos del revendedor</h3>";
    const pagos = await api("/vendedor/revendedores/" + revId + "/pagos", "GET");
    if (!pagos.length) html += "<p class='chico'>Sin pagos registrados.</p>";
    else {
      html += "<table><tr><th>Fecha</th><th>Sorteo</th><th>Jugadas</th><th>Monto</th></tr>";
      pagos.forEach(p => { html += "<tr><td>" + fmtFecha(p.creado_en) + "</td><td>#" + p.sorteo_id + " " + p.sorteo_titulo + "</td><td>" + p.cantidad_jugadas + "</td><td>$" + p.monto + "</td></tr>"; });
      html += "</table>";
    }
    caja.innerHTML = html;
  } catch (e) { caja.innerHTML = "<p class='mensaje error'>" + e.message + "</p>"; }
}

async function asignarCupoRev(revId) {
  const sorteoId = document.getElementById("vrev-gestion-sorteo").value;
  const cant = parseInt(document.getElementById("vrev-gestion-cant").value, 10);
  if (!sorteoId || !cant || cant < 1) { aviso("Completa sorteo y cantidad", true); return; }
  if (!confirm("Vas a ceder " + cant + " cupos de TU cupo a este revendedor para el sorteo #" + sorteoId + ". Continuar?")) return;
  try {
    await api("/vendedor/revendedores/" + revId + "/cupos", "POST", { sorteo_id: parseInt(sorteoId), cantidad: cant });
    aviso("Cupos cedidos al revendedor.");
    cargarGestionRev();
  } catch (e) { aviso(e.message, true); }
}

async function registrarPagoRev(revId) {
  const sorteoId = document.getElementById("vrev-pago-sorteo").value;
  const cant = parseInt(document.getElementById("vrev-pago-cant").value, 10);
  if (!sorteoId || !cant || cant < 1) { aviso("Completa sorteo y cantidad", true); return; }
  if (!confirm("Confirmas que el revendedor te pago " + cant + " jugadas del sorteo #" + sorteoId + "?")) return;
  try {
    const d = await api("/vendedor/revendedores/" + revId + "/pagos", "POST", { sorteo_id: parseInt(sorteoId), cantidad_jugadas: cant });
    aviso("Pago confirmado: " + d.cantidad_jugadas + " jugadas por $" + d.monto + ".");
    cargarGestionRev();
  } catch (e) { aviso(e.message, true); }
}
