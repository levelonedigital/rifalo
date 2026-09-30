// ---------- MODALIDADES Y REGLAS (admin) ----------
async function cargarModalidades() {
  MODALIDADES = await api("/admin/modalidades", "GET");
  const sel = document.getElementById("sorteo-modalidad");
  sel.innerHTML = MODALIDADES.map(m => "<option value='" + m.clave + "'>" + m.nombre + " (" + m.cantidad_numeros + " numeros)</option>").join("");
  pintarReglasModalidad();
}

function pintarReglasModalidad() {
  const sel = document.getElementById("sorteo-modalidad");
  if (!sel) return;
  const clave = sel.value;
  const m = MODALIDADES.find(x => x.clave === clave);
  document.getElementById("reglas-modalidad").textContent = m ? m.resumen_reglas : "";
  const esRifa = m && m.usa_premio_fijo;
  document.getElementById("caja-premio-fijo").style.display = esRifa ? "block" : "none";
  document.getElementById("caja-minimo").style.display = esRifa ? "block" : "none";
  if (!sorteo_edit_id && m) {
    document.getElementById("sorteo-detalle").value = m.resumen_reglas + " Si no se cumplen las condiciones, el sorteo puede pasar a otro horario; se respetan las jugadas.";
  }
}

// ---------- ADMIN: SORTEOS ----------
async function iniciarSorteos() {
  await cargarModalidades();
  await cargarSistema();
  await cargarPlantillas();
  cargarSorteos();
}

async function cargarSistema() {
  try {
    const s = await api("/admin/sistema", "GET");
    document.getElementById("sis-horarios").value = JSON.stringify(s.horarios);
    document.getElementById("sis-semhor").value = s.semanal_horario;
    document.getElementById("sis-semini").value = s.semanal_dia_inicio;
    document.getElementById("sis-semfin").value = s.semanal_dia_fin;
    document.getElementById("sis-busini").value = s.busqueda_inicio_min;
    document.getElementById("sis-busint").value = s.busqueda_intervalo_min;
    document.getElementById("sis-busdur").value = s.busqueda_duracion_min;
    document.getElementById("sis-vendpct").value = s.vendedor_pct;
    document.getElementById("sorteo-horario").innerHTML = Object.keys(s.horarios).map(h => "<option value='" + h + "'>" + h + " " + s.horarios[h] + "</option>").join("");
  } catch (e) { /* secundario sin permiso */ }
}

async function guardarSistema() {
  const cuerpo = {
    horarios: document.getElementById("sis-horarios").value,
    semanal_horario: document.getElementById("sis-semhor").value,
    semanal_dia_inicio: parseInt(document.getElementById("sis-semini").value),
    semanal_dia_fin: parseInt(document.getElementById("sis-semfin").value),
    busqueda_inicio_min: parseInt(document.getElementById("sis-busini").value),
    busqueda_intervalo_min: parseInt(document.getElementById("sis-busint").value),
    busqueda_duracion_min: parseInt(document.getElementById("sis-busdur").value),
    vendedor_pct: parseFloat(document.getElementById("sis-vendpct").value),
  };
  try { await api("/admin/sistema", "PUT", cuerpo); aviso("Sistema guardado"); }
  catch (e) { aviso(e.message, true); }
}

function leerFormSorteo() {
  const cuerpo = {
    modalidad: document.getElementById("sorteo-modalidad").value,
    horario: document.getElementById("sorteo-horario").value,
    fecha: document.getElementById("sorteo-fecha").value,
    precio_jugada: parseFloat(document.getElementById("sorteo-precio").value),
    pozo_base: parseFloat(document.getElementById("sorteo-pozobase").value || 0),
    casa_pct: parseFloat(document.getElementById("sorteo-casa").value),
    titulo: document.getElementById("sorteo-titulo").value || null,
  };
  const cierre = document.getElementById("sorteo-cierre").value;
  if (cierre) cuerpo.hora_cierre = cierre;
  const vend = document.getElementById("sorteo-vend").value;
  if (vend) cuerpo.vendedor_pct = parseFloat(vend);
  const premio = document.getElementById("sorteo-premio").value;
  if (premio) cuerpo.premio_fijo = parseFloat(premio);
  const minimo = document.getElementById("sorteo-minimo").value;
  if (minimo) cuerpo.minimo_cubrir = parseFloat(minimo);
  const img = document.getElementById("sorteo-imagen").value;
  if (img) cuerpo.imagen_url = img;
  const detalle = document.getElementById("sorteo-detalle").value;
  if (detalle) cuerpo.detalle = detalle;
  return cuerpo;
}

async function crearSorteo() {
  const cuerpo = leerFormSorteo();
  try {
    const d = await api("/admin/sorteos", "POST", cuerpo);
    aviso("Sorteo #" + d.id + " creado EN PREPARACION (inactivo). Revisalo, editalo si hace falta y recien ahi activalo.");
    cargarSorteos();
  }
  catch (e) { aviso(e.message, true); }
}

async function activarSorteo(id) {
  try { await api("/admin/sorteos/" + id + "/activar", "POST"); aviso("Sorteo #" + id + " ACTIVADO: ya lo ven vendedores, revendedores y jugadores"); cargarSorteos(); }
  catch (e) { aviso(e.message, true); }
}

async function desactivarSorteo(id) {
  try { await api("/admin/sorteos/" + id + "/desactivar", "POST"); aviso("Sorteo #" + id + " desactivado: vuelve a preparacion, nadie mas lo ve"); cargarSorteos(); }
  catch (e) { aviso(e.message, true); }
}

function empezarEdicion(id) {
  const s = SORT_CACHE[id];
  if (!s) return;
  sorteo_edit_id = id;
  document.getElementById("sorteo-horario").value = s.horario;
  document.getElementById("sorteo-fecha").value = s.fecha.slice(0,10);
  document.getElementById("sorteo-cierre").value = s.hora_cierre || "";
  document.getElementById("sorteo-precio").value = s.precio_jugada;
  document.getElementById("sorteo-pozobase").value = s.pozo_base;
  document.getElementById("sorteo-casa").value = s.casa_pct;
  document.getElementById("sorteo-vend").value = s.vendedor_pct ?? "";
  document.getElementById("sorteo-premio").value = s.premio_fijo ?? "";
  document.getElementById("sorteo-minimo").value = s.minimo_cubrir ?? "";
  document.getElementById("sorteo-titulo").value = s.titulo || "";
  document.getElementById("sorteo-imagen").value = s.imagen_url || "";
  document.getElementById("sorteo-detalle").value = s.detalle || "";
  document.getElementById("btn-crear").style.display = "none";
  const bar = document.getElementById("editar-bar");
  bar.style.display = "block";
  bar.innerHTML = "Editando sorteo #" + id + ". Modificá los campos del formulario de arriba y guarda. <button onclick='guardarEdicion()'>Guardar cambios</button><button class='peligro' onclick='cancelarEdicion()'>Cancelar edicion</button>";
  document.getElementById("editar-bar").scrollIntoView({ behavior: "smooth" });
}

function cancelarEdicion() {
  sorteo_edit_id = null;
  document.getElementById("editar-bar").style.display = "none";
  document.getElementById("btn-crear").style.display = "";
  pintarReglasModalidad();
}

async function guardarEdicion() {
  const cuerpo = leerFormSorteo();
  delete cuerpo.modalidad;
  try {
    await api("/admin/sorteos/" + sorteo_edit_id, "PUT", cuerpo);
    aviso("Sorteo #" + sorteo_edit_id + " actualizado");
    cancelarEdicion();
    cargarSorteos();
  } catch (e) { aviso(e.message, true); }
}

async function borrarSorteo(id) {
  if (!confirm("Borrar el sorteo #" + id + "? Solo se puede si todavia no tiene jugadas cargadas.")) return;
  try { await api("/admin/sorteos/" + id, "DELETE"); aviso("Sorteo #" + id + " borrado"); cargarSorteos(); }
  catch (e) { aviso(e.message, true); }
}

async function guardarPlantilla() {
  const nombre = document.getElementById("plantilla-nombre").value;
  if (!nombre) { aviso("Ponele un nombre a la guia", true); return; }
  const cuerpo = leerFormSorteo();
  cuerpo.nombre = nombre;
  delete cuerpo.fecha;
  delete cuerpo.hora_cierre;
  delete cuerpo.imagen_url;
  delete cuerpo.detalle;
  delete cuerpo.titulo;
  try { await api("/admin/plantillas", "POST", cuerpo); aviso("Guia guardada: " + nombre); cargarPlantillas(); }
  catch (e) { aviso(e.message, true); }
}

async function cargarPlantillas() {
  try {
    const ps = await api("/admin/plantillas", "GET");
    document.getElementById("plantillas-select").innerHTML = ps.map(p => "<option value='" + p.id + "'>" + p.nombre + " (" + p.modalidad + ")</option>").join("") || "<option value=''>No hay guias guardadas</option>";
  } catch (e) { /* sin permiso */ }
}

async function cargarPlantillaSel() {
  const id = document.getElementById("plantillas-select").value;
  if (!id) return;
  const ps = await api("/admin/plantillas", "GET");
  const p = ps.find(x => String(x.id) === String(id));
  if (!p) return;
  cancelarEdicion();
  document.getElementById("sorteo-modalidad").value = p.modalidad;
  pintarReglasModalidad();
  if (p.horario) document.getElementById("sorteo-horario").value = p.horario;
  document.getElementById("sorteo-precio").value = p.precio_jugada;
  document.getElementById("sorteo-pozobase").value = p.pozo_base;
  document.getElementById("sorteo-casa").value = p.casa_pct;
  document.getElementById("sorteo-vend").value = p.vendedor_pct ?? "";
  document.getElementById("sorteo-premio").value = p.premio_fijo ?? "";
  aviso("Guia cargada, pone el dia, el cierre y el titulo y crea el sorteo");
}

async function borrarPlantillaSel() {
  const id = document.getElementById("plantillas-select").value;
  if (!id) return;
  try { await api("/admin/plantillas/" + id, "DELETE"); aviso("Guia borrada"); cargarPlantillas(); }
  catch (e) { aviso(e.message, true); }
}

async function cargarSorteos() {
  try {
    const sorteos = await api("/admin/sorteos", "GET");
    sorteos.forEach(s => { SORT_CACHE[s.id] = s; });
    let html = "<table><tr><th>#</th><th>Img</th><th>Sorteo</th><th>Horario</th><th>Dia</th><th>Cierre</th><th>Estado</th><th>Pozo</th><th>Cubriendo / costo</th><th>Vendido</th><th>Ganadores</th><th>Acciones</th></tr>";
    sorteos.forEach(s => {
      const celdaNombre = "<td><b>" + (s.titulo || s.modalidad) + "</b>" + (s.titulo ? "<div class='chico'>" + s.modalidad + "</div>" : "") + (s.solo_participantes ? " <span class='chico'>VACANTE</span>" : "") + "</td>";
      const celdaGanadores = "<td>" + ((s.ganadores && s.ganadores.length) ? s.ganadores.join(", ") : "-") + "</td>";
      html += "<tr><td>" + s.id + "</td><td>" + (s.imagen_url ? "<img src='" + s.imagen_url + "' style='width:44px;height:44px;object-fit:cover;border-radius:4px'>" : "-") + "</td>" + celdaNombre + "<td>" + s.horario + "</td><td>" + fmtFecha(s.fecha) + "</td><td>" + (s.hora_cierre || "sin limite") + "</td><td>" + s.estado + (s.busqueda_agotada ? " (manual)" : "") + "</td><td>$" + s.pozo + "</td><td>$" + s.pozo_cubierto + " / $" + s.costo + (s.costo_cubierto ? " ✔" : " ✘") + "</td><td>$" + (s.recaudado || 0) + "</td>" + celdaGanadores + "<td>";
      html += "<button class='secundario' onclick='seleccionarSorteo(" + s.id + ")'>Detalles</button>";
      if (s.estado === "preparacion") html += "<button onclick='activarSorteo(" + s.id + ")'>Activar</button>";
      if (s.estado === "programado") html += "<button class='secundario' onclick='cerrarSorteo(" + s.id + ")'>Cerrar</button><button class='secundario' onclick='desactivarSorteo(" + s.id + ")'>Desactivar</button><button class='peligro' onclick='cancelarHorario(" + s.id + ")'>Cancelar horario</button>";
      if (s.estado === "cerrado") html += "<button onclick='cargarResultado(" + s.id + ")'>Cargar 20 nums</button><button class='peligro' onclick='cancelarHorario(" + s.id + ")'>Cancelar horario</button>";
      if (s.estado === "reprogramando") html += "<button onclick='prepararReprog(" + s.id + ")'>Reprogramar</button>";
      if (s.estado !== "liquidado") {
        html += "<button class='secundario' onclick='empezarEdicion(" + s.id + ")'>Editar</button>";
        html += "<button class='peligro' onclick='borrarSorteo(" + s.id + ")'>Borrar</button>";
      }
      if (s.estado === "liquidado") html += "<button class='secundario' onclick='pozoVacante(" + s.id + ")'>Pozo vacante</button>";
      html += "</td></tr>";
    });
    document.getElementById("lista-sorteos").innerHTML = html + "</table>";
  } catch (e) { aviso(e.message, true); }
}

async function prepararReprog(id) {
  const texto = prompt("Nuevo dia del sorteo (DD-MM-AAAA o AAAA-MM-DD), ej: 23-09-2026:");
  if (!texto) return;
  const fecha = aIsoFecha(texto);
  if (!fecha) { aviso("Fecha invalida, usa DD-MM-AAAA o AAAA-MM-DD", true); return; }
  try {
    await api("/admin/sorteos/" + id + "/reprogramar", "POST", { fecha: fecha });
    aviso("Sorteo #" + id + " reprogramado: se aviso a los jugadores con el nuevo dia");
    cargarSorteos();
    cargarAvisos();
  } catch (e) { aviso(e.message, true); }
}

async function cerrarSorteo(id) {
  try { await api("/admin/sorteos/" + id + "/cerrar", "POST"); aviso("Sorteo cerrado: el buscador automatico ya puede trabajar"); cargarSorteos(); }
  catch (e) { aviso(e.message, true); }
}

async function cancelarHorario(id) {
  try { await api("/admin/sorteos/" + id + "/cancelar-horario", "POST"); aviso("Horario cancelado: jugadas y pozo siguen en juego, se aviso a los jugadores"); cargarSorteos(); cargarAvisos(); }
  catch (e) { aviso(e.message, true); }
}

async function cargarResultado(id) {
  const texto = prompt("Pega los 20 numeros oficiales separados por coma (1er premio primero):");
  if (!texto) return;
  try {
    const d = await api("/admin/sorteos/" + id + "/resultado", "POST", { numeros: parseNumeros(texto) });
    let detalle;
    if (d.ganadoras && d.ganadoras.length) {
      const porJugada = Math.round((d.pozo_pagado / d.ganadoras.length) * 100) / 100;
      detalle = "Liquidado.\nGanadoras: jugadas " + d.ganadoras.join(", ") + ".\nPozo pagado: $" + d.pozo_pagado + " ($" + porJugada + " por jugada ganadora).";
    } else {
      detalle = "Liquidado sin ganadoras.\nPozo retenido: $" + d.pozo_sin_ganador + ".";
    }
    aviso(detalle);
    cargarSorteos();
  } catch (e) { aviso(e.message, true); }
}

async function pozoVacante(id) {
  const texto = prompt("Dia del sorteo vacante (DD-MM-AAAA o AAAA-MM-DD):");
  if (!texto) return;
  const fecha = aIsoFecha(texto);
  if (!fecha) { aviso("Fecha invalida, usa DD-MM-AAAA o AAAA-MM-DD", true); return; }
  try { const d = await api("/admin/sorteos/" + id + "/pozo-vacante", "POST", { fecha: fecha }); aviso("Pozo vacante #" + d.id + " creado en preparacion con $" + d.pozo_inicial + ". Activalo cuando este listo."); cargarSorteos(); }
  catch (e) { aviso(e.message, true); }
}

// ---------- ADMIN: BUSCADOR ----------
async function cargarEstadoBuscador() {
  const cont = document.getElementById("estado-buscador");
  if (!cont) return;
  try {
    const d = await api("/admin/buscador/estado", "GET");
    let html = "";
    if (d.sorteos_cerrados_sin_resultado && d.sorteos_cerrados_sin_resultado.length > 0) {
      html += "<h3 style='color:#93c5fd;margin-top:8px'>Sorteos cerrados esperando resultado</h3>";
      d.sorteos_cerrados_sin_resultado.forEach(s => {
        html += "<div class='buscador-box'><b>Sorteo #" + s.id + "</b> - " + s.modalidad + " " + s.horario + " (" + fmtFecha(s.fecha) + ")</div>";
      });
    } else {
      html += "<p class='chico'>No hay sorteos cerrados esperando resultado.</p>";
    }
    if (d.busquedas_en_curso && Object.keys(d.busquedas_en_curso).length > 0) {
      html += "<h3 style='color:#93c5fd;margin-top:16px'>Búsquedas en curso</h3>";
      for (const [sorteoId, estado] of Object.entries(d.busquedas_en_curso)) {
        html += "<div class='buscador-box'>";
        html += "<b>Sorteo #" + sorteoId + "</b> - " + estado.cantidad_lecturas + " lecturas<br>";
        if (estado.ultima_lectura && estado.ultima_lectura.length > 0) {
          html += "<span class='nums'>Última lectura: " + estado.ultima_lectura.map(n => String(n).padStart(2,'0')).join(", ") + "</span><br>";
        }
        if (estado.coinciden_ultimas_tres) {
          html += "<span class='ok'>✔ Las últimas 3 lecturas coinciden - confirmando resultado</span>";
        } else if (estado.cantidad_lecturas >= 2) {
          html += "<span class='warn'>⚠ Lecturas aún no coinciden (" + estado.cantidad_lecturas + "/3)</span>";
        } else {
          html += "<span class='chico'>Esperando más lecturas...</span>";
        }
        html += "</div>";
      }
    } else {
      html += "<p class='chico' style='margin-top:12px'>No hay búsquedas en curso en este momento.</p>";
    }
    cont.innerHTML = html;
  } catch (e) {
    cont.innerHTML = "<p class='mensaje error'>Error al cargar el estado: " + e.message + "</p>";
  }
}

// ---------- ADMIN: VENDEDORES ----------
async function crearVendedor() {
  const cuerpo = {
    usuario: document.getElementById("vend-usuario").value,
    password: document.getElementById("vend-password").value,
    nombre: document.getElementById("vend-nombre").value,
    telefono: document.getElementById("vend-telefono").value || null,
    codigo: document.getElementById("vend-codigo").value,
    comision_pct: parseFloat(document.getElementById("vend-comision").value),
    datos_transferencia: document.getElementById("vend-transferencia").value || null,
  };
  try { await api("/admin/vendedores", "POST", cuerpo); aviso("Vendedor creado"); cargarVendedores(); }
  catch (e) { aviso(e.message, true); }
}

async function cargarVendedores() {
  try {
    const jt = await api("/admin/jugadores-total", "GET");
    document.getElementById("caja-jugadores-total").innerHTML = "Jugadores registrados en la app: <span>" + jt.total + "</span> (activos: " + jt.activos + ")";
  } catch (e) { /* ignora */ }
  try {
    const vs = await api("/admin/vendedores", "GET");
    VEND_CACHE = {};
    vs.forEach(v => { VEND_CACHE[v.id] = v; });
    let html = "<table><tr><th>#</th><th>Usuario</th><th>Nombre</th><th>Codigo</th><th>Comision</th><th>Activo</th><th>Acciones</th></tr>";
    vs.forEach(v => {
      html += "<tr><td>" + v.id + "</td><td>" + v.usuario + "</td><td>" + v.nombre + "</td><td>" + v.codigo + "</td><td>" + v.comision_pct + "%</td><td>" + (v.activo ? "si" : "no") + "</td><td><button class='secundario' onclick='empezarEdicionVendedor(" + v.id + ")'>Editar</button></td></tr>";
    });
    document.getElementById("lista-vendedores").innerHTML = html + "</table>";
  } catch (e) { aviso(e.message, true); }
}

function empezarEdicionVendedor(id) {
  const v = VEND_CACHE[id];
  if (!v) return;
  vendedor_edit_id = id;
  const bar = document.getElementById("vended-edit-bar");
  bar.style.display = "block";
  bar.innerHTML =
    "Editando vendedor " + v.usuario + "." +
    "<div class='grilla'>" +
    "<div><label>Nombre</label><input id='ve-nombre'></div>" +
    "<div><label>Telefono</label><input id='ve-telefono'></div>" +
    "<div><label>Codigo</label><input id='ve-codigo'></div>" +
    "<div><label>Comision %</label><input id='ve-comision' type='number'></div>" +
    "<div><label>Nueva contrasenia (vacio = no cambiar)</label><input id='ve-password' type='password'></div>" +
    "<div><label>Datos de transferencia</label><input id='ve-transferencia'></div>" +
    "</div>" +
    "<div class='check-linea'><input type='checkbox' id='ve-activo'><span>Vendedor activo</span></div>" +
    "<button onclick='guardarEdicionVendedor()'>Guardar cambios</button><button class='peligro' onclick='cancelarEdicionVendedor()'>Cancelar</button>";
  document.getElementById("ve-nombre").value = v.nombre || "";
  document.getElementById("ve-telefono").value = v.telefono || "";
  document.getElementById("ve-codigo").value = v.codigo || "";
  document.getElementById("ve-comision").value = v.comision_pct;
  document.getElementById("ve-transferencia").value = v.datos_transferencia || "";
  document.getElementById("ve-password").value = "";
  document.getElementById("ve-activo").checked = Boolean(v.activo);
  bar.scrollIntoView({ behavior: "smooth" });
}

function cancelarEdicionVendedor() {
  vendedor_edit_id = null;
  document.getElementById("vended-edit-bar").style.display = "none";
}

async function guardarEdicionVendedor() {
  const cuerpo = {
    nombre: document.getElementById("ve-nombre").value,
    telefono: document.getElementById("ve-telefono").value || null,
    codigo: document.getElementById("ve-codigo").value,
    comision_pct: parseFloat(document.getElementById("ve-comision").value),
    datos_transferencia: document.getElementById("ve-transferencia").value || null,
    activo: document.getElementById("ve-activo").checked,
  };
  const pass = document.getElementById("ve-password").value;
  if (pass) cuerpo.password = pass;
  try {
    await api("/admin/vendedores/" + vendedor_edit_id, "PUT", cuerpo);
    aviso("Vendedor actualizado");
    cancelarEdicionVendedor();
    cargarVendedores();
  } catch (e) { aviso(e.message, true); }
}

// ---------- ADMIN: JUGADAS ----------
async function iniciarJugadas() {
  if (SORT_ACTUAL) {
    document.getElementById("jugadas-selector").style.display = "none";
    document.getElementById("jugadas-estado-filtro").style.display = "block";
  } else {
    document.getElementById("jugadas-selector").style.display = "grid";
    document.getElementById("jugadas-estado-filtro").style.display = "none";
    await llenarSelectJugadasSorteos();
  }
  cargarJugadasAdmin();
}

async function llenarSelectJugadasSorteos() {
  try {
    const sorteos = await api("/admin/sorteos", "GET");
    sorteos.forEach(s => { SORT_CACHE[s.id] = s; });
    document.getElementById("jugadas-sorteo").innerHTML = "<option value=''>Elegi un sorteo para ver sus jugadas...</option>" +
      sorteos.map(s => "<option value='" + s.id + "'>#" + s.id + " " + (s.titulo || s.modalidad) + " " + s.horario + " " + fmtFecha(s.fecha) + " (" + s.estado + ")</option>").join("");
  } catch (e) { aviso(e.message, true); }
}

async function cargarJugadasAdmin() {
  const enModo = Boolean(SORT_ACTUAL);
  const sorteoId = enModo ? SORT_ACTUAL : document.getElementById("jugadas-sorteo").value;
  const estado = enModo ? document.getElementById("jugadas-filtro-modo").value : document.getElementById("jugadas-filtro").value;
  const caja = document.getElementById("lista-jugadas-admin");
  if (!sorteoId) {
    caja.innerHTML = "<p class='chico'>Seleccioná un sorteo para ver sus jugadas (o usa el boton Detalles en la pestana Sorteos).</p>";
    return;
  }
  let ruta = "/admin/jugadas?sorteo_id=" + sorteoId;
  if (estado) ruta += "&estado=" + estado;
  try {
    const js = await api(ruta, "GET");
    if (!js.length) { caja.innerHTML = "<p class='chico'>Este sorteo no tiene jugadas con ese filtro.</p>"; return; }
    let html = "<table><tr><th>#</th><th>Jugador</th><th>Vendedor</th><th>Numeros</th><th>Precio</th><th>Estado</th><th>Premio</th><th></th></tr>";
    js.forEach(j => {
      html += "<tr><td>" + j.id + "</td><td>" + (j.jugador_nombre || "-") + "</td><td>" + j.vendedor + "</td><td>" + j.numeros + "</td><td>$" + j.precio + "</td><td>" + j.estado + "</td><td>$" + (j.premio ?? "-") + "</td><td><button class='secundario' onclick='verJugada(" + j.id + ")'>Ver</button></td></tr>";
    });
    caja.innerHTML = html + "</table>";
  } catch (e) { aviso(e.message, true); }
}

async function verJugada(id) {
  try {
    const j = await api("/admin/jugadas/" + id, "GET");
    const s = j.sorteo || {};
    document.getElementById("jugada-detalle").textContent =
      "JUGADA #" + j.id +
      "\nSorteo: #" + (s.id || "-") + " " + (s.modalidad || "") + " " + (s.horario || "") + " " + fmtFecha(s.fecha) + " (" + (s.estado || "") + ")" +
      "\nVendedor: " + j.vendedor +
      "\nRevendedor: " + (j.revendedor || "sin revendedor") +
      "\nJugador: " + (j.jugador_nombre || "-") + (j.jugador_usuario ? " (usuario " + j.jugador_usuario + ")" : "") +
      "\nNumeros: " + j.numeros +
      "\nPrecio: $" + j.precio +
      "\nEstado: " + j.estado +
      "\nPremio: $" + (j.premio ?? 0) + (j.estado === "ganadora" ? (j.premio_pagado ? " (PAGADO)" : " (PENDIENTE DE PAGO)") : "") +
      (j.estado === "ganadora" ? (j.premio_cobrado ? " - el jugador CONFIRMO QUE COBRO" : " - el jugador aun no confirmo el cobro") : "") +
      "\nReparto: casa $" + (j.monto_casa ?? 0) + " | vendedor $" + (j.monto_vendedor ?? 0) + (j.comision_pagada ? " (comision PAGADA)" : " (comision PENDIENTE)") + " | revendedor $" + (j.monto_revendedor ?? 0) + " | pozo $" + (j.monto_pozo ?? 0) + " | cubrir $" + (j.monto_cubrir ?? 0) +
      "\nCargada: " + ((j.creada_en || "").slice(0,19).replace("T"," "));
  } catch (e) { aviso(e.message, true); }
}

// ---------- ADMIN: RESUMEN + LIQUIDACION ----------
async function cargarResumen() {
  const cajaLiq = document.getElementById("caja-liquidacion");
  cajaLiq.innerHTML = "";
  try {
    if (SORT_ACTUAL) {
      const r = await api("/admin/sorteos/" + SORT_ACTUAL + "/resumen", "GET");
      document.getElementById("caja-resumen").innerHTML =
        "<table><tr><th>Sorteo</th><th>Estado</th><th>Jugadas</th><th>Vendido</th><th>Casa</th><th>Vendedores</th><th>Revend.</th><th>Pozo</th><th>Pozo cubierto</th><th>Premios</th><th>Ganadoras</th></tr>" +
        "<tr><td>#" + r.sorteo_id + " " + r.modalidad + " " + r.horario + "</td><td>" + r.estado + "</td><td>" + r.jugadas_vendidas + "</td><td>$" + r.vendido + "</td><td>$" + r.casa + "</td><td>$" + r.vendedores + "</td><td>$" + r.revendedores + "</td><td>$" + r.pozo + "</td><td>$" + r.pozo_cubierto + " / $" + r.costo + (r.costo_cubierto ? " ✔" : " ✘") + "</td><td>$" + r.premios_pagados + "</td><td>" + (r.ganadoras.join(", ") || "-") + "</td></tr></table>" +
        "<p class='chico'>Recaudado $" + r.recaudado + ". Pozo aportado (cobertura + extra): $" + r.pozo_aportado + ". Resultados: " + (r.resultados || "sin cargar") + "</p>";
      if (r.estado === "liquidado") await cargarLiquidacion(SORT_ACTUAL);
      return;
    }
    const r = await api("/admin/resumen-general", "GET");
    document.getElementById("caja-resumen").innerHTML = "<table><tr><th>Jugadas</th><th>Vendido</th><th>Casa</th><th>Vendedores</th><th>Revendedores</th><th>Premios</th></tr><tr><td>" + r.jugadas_aprobadas + "</td><td>$" + r.vendido + "</td><td>$" + r.casa + "</td><td>$" + r.vendedores + "</td><td>$" + r.revendedores + "</td><td>$" + r.premios_pagados + "</td></tr></table>";
  } catch (e) { aviso(e.message, true); }
}

async function cargarLiquidacion(sorteoId) {
  try {
    const d = await api("/admin/sorteos/" + sorteoId + "/liquidacion", "GET");
    let html = "<h2>Detalle de liquidacion</h2>";
    html += "<p><b>Resultados oficiales:</b> " + (d.resultados || "-") + "</p>";
    html += "<p><b>Pozo formado:</b> $" + d.pozo_formado + " | <b>Pozo pagado en premios:</b> $" + d.pozo_pagado + " | <b>Ganadores:</b> " + d.cantidad_ganadoras + "</p>";
    html += "<p><b>Ganancia casa (admin):</b> $" + d.casa + " | <b>Vendedores:</b> $" + d.vendedores + " | <b>Revendedores:</b> $" + d.revendedores + "</p>";
    if (d.ganadoras.length) {
      html += "<table><tr><th>Jugada</th><th>Ganador</th><th>Numeros ganadores</th><th>Premio</th><th>Premio pagado</th><th>Jugador cobro</th><th>Vendedor</th><th>Comision pagada</th></tr>";
      d.ganadoras.forEach(g => {
        html += "<tr><td>#" + g.jugada_id + "</td><td>" + g.jugador + "</td><td>" + g.numeros + "</td><td>$" + g.premio + "</td>" +
          "<td>" + (g.premio_pagado ? "✔ PAGADO" : "✘ PENDIENTE") + " <button class='secundario' onclick='marcarPremio(" + g.jugada_id + "," + (!g.premio_pagado) + ")'>" + (g.premio_pagado ? "Desmarcar" : "Marcar pagado") + "</button></td>" +
          "<td>" + (g.premio_cobrado ? "✔ CONFIRMO COBRO" : "✘ no confirmo") + "</td>" +
          "<td>" + g.vendedor + "</td>" +
          "<td>" + (g.comision_pagada ? "✔ PAGADA" : "✘ PENDIENTE") + " <button class='secundario' onclick='marcarComision(" + g.jugada_id + "," + (!g.comision_pagada) + ")'>" + (g.comision_pagada ? "Desmarcar" : "Marcar pagada") + "</button></td></tr>";
      });
      html += "</table>";
    } else {
      html += "<p class='chico'>Este sorteo no tuvo ganadores; el pozo queda retenido para el pozo vacante.</p>";
    }
    document.getElementById("caja-liquidacion").innerHTML = html;
  } catch (e) { /* ignora */ }
}

async function marcarPremio(jugadaId, pagado) {
  try { await api("/admin/jugadas/" + jugadaId + "/marcar-premio", "POST", { pagado: pagado }); cargarResumen(); }
  catch (e) { aviso(e.message, true); }
}

async function marcarComision(jugadaId, pagado) {
  try { await api("/admin/jugadas/" + jugadaId + "/marcar-comision", "POST", { pagado: pagado }); cargarResumen(); }
  catch (e) { aviso(e.message, true); }
}

// ---------- ADMIN: BALANCE ----------
async function cargarBalance() {
  const periodo = document.getElementById("bal-periodo").value;
  const fechaVal = document.getElementById("bal-fecha").value;
  let ruta = "/admin/balance?periodo=" + periodo;
  if (fechaVal) ruta += "&fecha=" + fechaVal;
  try {
    const d = await api(ruta, "GET");
    let html = "<p><b>Periodo:</b> " + periodo + " | <b>Desde:</b> " + fmtFecha(d.desde) + " | <b>Hasta:</b> " + fmtFecha(d.hasta) + " | <b>Sorteos liquidados:</b> " + d.sorteos_liquidados + "</p>";
    html += "<table><tr><th>Vendido</th><th>Casa (ganancia admin)</th><th>Vendedores</th><th>Revendedores</th><th>Pozo formado</th><th>Premios pagados</th></tr>" +
      "<tr><td>$" + d.totales.vendido + "</td><td>$" + d.totales.casa + "</td><td>$" + d.totales.vendedores + "</td><td>$" + d.totales.revendedores + "</td><td>$" + d.totales.pozo_formado + "</td><td>$" + d.totales.premios + "</td></tr></table>";
    if (d.por_sorteo.length) {
      html += "<h3 style='color:#93c5fd;margin-top:12px'>Detalle por sorteo</h3>";
      html += "<table><tr><th>#</th><th>Modalidad</th><th>Horario</th><th>Dia</th><th>Vendido</th><th>Casa</th><th>Vendedores</th><th>Pozo</th><th>Premios</th></tr>";
      d.por_sorteo.forEach(s => {
        html += "<tr><td>" + s.sorteo_id + "</td><td>" + s.modalidad + "</td><td>" + s.horario + "</td><td>" + fmtFecha(s.fecha) + "</td><td>$" + s.vendido + "</td><td>$" + s.casa + "</td><td>$" + s.vendedores + "</td><td>$" + s.pozo_formado + "</td><td>$" + s.premios + "</td></tr>";
      });
      html += "</table>";
    } else {
      html += "<p class='chico'>No hay sorteos liquidados en este periodo.</p>";
    }
    document.getElementById("caja-balance").innerHTML = html;
  } catch (e) { aviso(e.message, true); }
}

// ---------- ADMIN: AUDITORIA ----------
function coincideSorteo(log, id, idsJugadas) {
  const d = log.detalle || "";
  if (d.includes("sorteo=" + id)) return true;
  if (d.includes("sorteo_id': " + id)) return true;
  if (d.includes("id=" + id + " ")) return true;
  for (const jid of idsJugadas) {
    if (d.includes("jugada=" + jid)) return true;
  }
  return false;
}

async function cargarAuditoria() {
  try {
    let logs = await api("/admin/auditoria?limite=300", "GET");
    if (SORT_ACTUAL) {
      const js = await api("/admin/jugadas?sorteo_id=" + SORT_ACTUAL, "GET");
      const ids = js.map(j => j.id);
      logs = logs.filter(l => coincideSorteo(l, SORT_ACTUAL, ids));
    }
    let html = "<table><tr><th>Fecha</th><th>Usuario</th><th>Accion</th><th>Detalle</th></tr>";
    logs.forEach(l => { html += "<tr><td>" + l.fecha.slice(0,19).replace("T"," ") + "</td><td>" + (l.nombre_usuario || "-") + "</td><td>" + l.accion + "</td><td>" + (l.detalle || "") + "</td></tr>"; });
    document.getElementById("lista-auditoria").innerHTML = html + "</table>";
  } catch (e) { aviso(e.message, true); }
}

// ---------- REGISTRO DE PESTANAS DEL ADMIN ----------
window.ACCIONES = window.ACCIONES || {};
ACCIONES.sorteos = iniciarSorteos;
ACCIONES.buscador = cargarEstadoBuscador;
ACCIONES.vendedores = cargarVendedores;
ACCIONES.jugadas = iniciarJugadas;
ACCIONES.resumen = cargarResumen;
ACCIONES.balance = cargarBalance;
ACCIONES.auditoria = cargarAuditoria;
