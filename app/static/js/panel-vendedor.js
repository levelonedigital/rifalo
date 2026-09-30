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
  try { const d = await api("/vendedor/jugadas", "POST", cuerpo); aviso("Jugada #" + d.id + " cargada"); document.getElementById("v-numeros").value = ""; }
  catch (e) { aviso(e.message, true); }
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
      html += "<span class='nums'>Numeros: " + r.resultados.map(n => String(n).padStart(2, "0")).join(", ") + "</span><br>";
      html += "<span class='chico'>Cantidad de ganadores: " + r.cantidad_ganadores + "</span><br>";
      if (r.mis_ganadores && r.mis_ganadores.length) {
        r.mis_ganadores.forEach(g => {
          html += "<div class='cobro-box'><b>Tu jugador " + g.jugador_nombre + " GANO $" + g.premio + "</b> (jugada #" + g.jugada_id + ").<br>";
          html += (g.premio_pagado ? "Marcado como entregado por vos. " : "<b>Pendiente de entrega.</b> ");
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

// ---------- REGISTRO DE PESTANAS DEL VENDEDOR ----------
window.ACCIONES = window.ACCIONES || {};
ACCIONES.vresumen = cargarVResumen;
ACCIONES.vcargar = () => { llenarSelectSorteos("/vendedor/sorteos", "v-sorteo"); cargarSelectJugadores("v"); };
ACCIONES.vpendientes = cargarVPendientes;
ACCIONES.vjugadas = cargarVJugadas;
ACCIONES.vrevendedores = cargarVRevendedores;
ACCIONES.vjugadores = cargarVJugadores;
