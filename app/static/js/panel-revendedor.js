// ---------- REVENDEDOR: SORTEOS Y JUGADAS ----------
async function cargarRSorteos() {
  try {
    const ss = await api("/revendedor/sorteos", "GET");
    let html = "<table><tr><th>#</th><th>Img</th><th>Sorteo</th><th>Horario</th><th>Dia</th><th>Cierre</th><th>Estado</th><th>Precio</th><th>Pozo actual</th></tr>";
    ss.forEach(s => { html += "<tr><td>" + s.id + "</td><td>" + (s.imagen_url ? "<img src='" + s.imagen_url + "' style='width:40px;height:40px;object-fit:cover;border-radius:4px'>" : "-") + "</td><td><b>" + nombreSorteo(s) + "</b>" + (s.titulo ? "<div class='chico'>" + s.modalidad + "</div>" : "") + (s.reprogramando ? " (REPROGRAMANDO)" : "") + "<div class='chico'>" + (s.detalle || "") + "</div></td><td>" + s.horario + "</td><td>" + fmtFecha(s.fecha) + "</td><td>" + (s.hora_cierre || "sin limite") + "</td><td>" + s.estado + "</td><td>$" + s.precio_jugada + "</td><td><b style='color:#22c55e'>$" + s.pozo + "</b></td></tr>"; });
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
  try { const d = await api("/revendedor/jugadas", "POST", cuerpo); aviso("Jugada #" + d.id + " cargada, la aprueba tu vendedor"); document.getElementById("r-numeros").value = ""; }
  catch (e) { aviso(e.message, true); }
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

// ---------- REGISTRO DE PESTANAS DEL REVENDEDOR ----------
window.ACCIONES = window.ACCIONES || {};
ACCIONES.rsorteos = cargarRSorteos;
ACCIONES.rcargar = () => { llenarSelectSorteos("/revendedor/sorteos", "r-sorteo"); cargarSelectJugadores("r"); };
ACCIONES.rjugadas = cargarRJugadas;
ACCIONES.rresumen = cargarRResumen;
ACCIONES.rjugadores = cargarRJugadores;
