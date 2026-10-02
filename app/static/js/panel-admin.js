let LIQ_CACHE = {};
let imagen_data_pending = null; // null = no cambiar; dataUri = subir; "" = quitar

// ---------- MODALIDADES Y BLOQUES POR MODALIDAD ----------
async function cargarModalidades() {
  MODALIDADES = await api("/admin/modalidades", "GET");
  const sel = document.getElementById("sorteo-modalidad");
  sel.innerHTML = MODALIDADES.map(m => "<option value='" + m.clave + "'>" + m.nombre + " (" + m.cantidad_numeros + " numeros)</option>").join("");
  cambiarModalidadSorteo();
}

function intOrNull(id) {
  const v = document.getElementById(id).value;
  return v === "" ? null : parseInt(v, 10);
}

function cambiarModalidadSorteo() {
  const clave = document.getElementById("sorteo-modalidad").value;
  const m = MODALIDADES.find(x => x.clave === clave);
  document.getElementById("reglas-modalidad").textContent = m ? m.resumen_reglas : "";
  document.getElementById("bloque-rifa").style.display = clave === "rifa" ? "block" : "none";
  document.getElementById("bloque-clasico").style.display = clave === "clasico" ? "block" : "none";
  document.getElementById("bloque-semanal").style.display = clave === "semanal" ? "block" : "none";
  if (!sorteo_edit_id && m) {
    document.getElementById("sorteo-detalle").value = m.resumen_reglas + " Si no se cumplen las condiciones, el sorteo puede pasar a otro horario; se respetan las jugadas.";
  }
}

// ---------- IMAGEN DE PRESENTACION ----------
function mostrarPreviewImagen(src) {
  const box = document.getElementById("sorteo-imagen-preview-box");
  const img = document.getElementById("sorteo-imagen-preview");
  if (!box || !img) return;
  if (src) { img.src = src; box.style.display = "block"; }
  else { img.removeAttribute("src"); box.style.display = "none"; }
}

async function subirImagenSorteo() {
  const input = document.getElementById("sorteo-imagen-file");
  const file = input && input.files && input.files[0];
  if (!file) return;
  try {
    const dataUri = await comprimirImagen(file, 900, 0.82);
    if (!dataUri) return;
    if (dataUri.length > 600000) { aviso("La imagen quedo muy pesada inclusive comprimida. Probá con una foto mas chica.", true); return; }
    imagen_data_pending = dataUri;
    mostrarPreviewImagen(dataUri);
    aviso("Imagen lista. Se guarda al crear/editar el sorteo.");
  } catch (e) { aviso(e.message, true); }
}

function quitarImagenSorteo() {
  imagen_data_pending = "";
  const input = document.getElementById("sorteo-imagen-file");
  if (input) input.value = "";
  const url = document.getElementById("sorteo-imagen");
  if (url) url.value = "";
  mostrarPreviewImagen(null);
}

function resetImagenForm() {
  imagen_data_pending = null;
  const input = document.getElementById("sorteo-imagen-file");
  if (input) input.value = "";
  mostrarPreviewImagen(null);
}

// ---------- ADMIN: SORTEOS ----------
async function iniciarSorteos() {
  await cargarModalidades();
  await cargarSistema();
  await cargarPlantillas();
  resetImagenForm();
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
  try { await api("/admin/sistema", "PUT", cuerpo); aviso("Sistema guardado (horarios oficiales y % default)"); }
  catch (e) { aviso(e.message, true); }
}

function leerFormSorteo() {
  const modalidad = document.getElementById("sorteo-modalidad").value;
  const cuerpo = {
    modalidad: modalidad,
    horario: document.getElementById("sorteo-horario").value,
    fecha: document.getElementById("sorteo-fecha").value,
    precio_jugada: parseFloat(document.getElementById("sorteo-precio").value),
    casa_pct: parseFloat(document.getElementById("sorteo-casa").value),
    titulo: document.getElementById("sorteo-titulo").value || null,
    busqueda_inicio_min: intOrNull("sorteo-busini"),
    busqueda_intervalo_min: intOrNull("sorteo-busint"),
    busqueda_duracion_min: intOrNull("sorteo-busdur"),
  };

  // Campos especificos de la modalidad activa.
  if (modalidad === "rifa") {
    const p = document.getElementById("rifa-premio").value;
    if (p) cuerpo.premio_fijo = parseFloat(p);
    cuerpo.premio_nombre = document.getElementById("rifa-premio-nombre").value || null;
    cuerpo.pozo_base = 0;
  } else if (modalidad === "semanal") {
    cuerpo.pozo_base = parseFloat(document.getElementById("semanal-pozobase").value || 0);
    cuerpo.semanal_dia_inicio = intOrNull("semanal-semi");
    cuerpo.semanal_dia_fin = intOrNull("semanal-semf");
  } else {
    cuerpo.pozo_base = parseFloat(document.getElementById("clasico-pozobase").value || 0);
  }

  const cierre = document.getElementById("sorteo-cierre").value;
  if (cierre) cuerpo.hora_cierre = cierre;
  const vend = document.getElementById("sorteo-vend").value;
  if (vend) cuerpo.vendedor_pct = parseFloat(vend);
  const url = document.getElementById("sorteo-imagen").value;
  if (url) cuerpo.imagen_url = url;
  const detalle = document.getElementById("sorteo-detalle").value;
  if (detalle) cuerpo.detalle = detalle;
  if (imagen_data_pending !== null) {
    cuerpo.imagen_data = imagen_data_pending;
    if (imagen_data_pending === "") cuerpo.imagen_url = "";
  }
  return cuerpo;
}

async function crearSorteo() {
  const cuerpo = leerFormSorteo();
  try {
    const d = await api("/admin/sorteos", "POST", cuerpo);
    aviso("Sorteo #" + d.id + " creado EN PREPARACION (inactivo) con titulo \"" + (d.titulo || "") + "\". Revisalo, editalo si hace falta y recien ahi activalo.");
    resetImagenForm();
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
  document.getElementById("sorteo-modalidad").value = s.modalidad;
  cambiarModalidadSorteo();
  // Especificos segun modalidad.
  if (s.modalidad === "rifa") {
    document.getElementById("rifa-premio").value = s.premio_fijo ?? "";
    document.getElementById("rifa-premio-nombre").value = s.premio_nombre || "";
  } else if (s.modalidad === "semanal") {
    document.getElementById("semanal-pozobase").value = s.pozo_base ?? "";
    document.getElementById("semanal-semi").value = s.semanal_dia_inicio ?? "";
    document.getElementById("semanal-semf").value = s.semanal_dia_fin ?? "";
  } else {
    document.getElementById("clasico-pozobase").value = s.pozo_base ?? "";
  }
  // Comunes.
  document.getElementById("sorteo-horario").value = s.horario;
  document.getElementById("sorteo-fecha").value = s.fecha.slice(0,10);
  document.getElementById("sorteo-cierre").value = s.hora_cierre || "";
  document.getElementById("sorteo-precio").value = s.precio_jugada;
  document.getElementById("sorteo-casa").value = s.casa_pct;
  document.getElementById("sorteo-vend").value = s.vendedor_pct ?? "";
  document.getElementById("sorteo-titulo").value = s.titulo || "";
  document.getElementById("sorteo-detalle").value = s.detalle || "";
  document.getElementById("sorteo-busini").value = s.busqueda_inicio_min ?? "";
  document.getElementById("sorteo-busint").value = s.busqueda_intervalo_min ?? "";
  document.getElementById("sorteo-busdur").value = s.busqueda_duracion_min ?? "";
  // Imagen.
  imagen_data_pending = null;
  const urlInput = document.getElementById("sorteo-imagen");
  const actual = s.imagen_url || "";
  if (actual.indexOf("data:") === 0) {
    if (urlInput) urlInput.value = "";
    mostrarPreviewImagen(actual);
  } else {
    if (urlInput) urlInput.value = actual;
    mostrarPreviewImagen(actual || null);
  }
  document.getElementById("btn-crear").style.display = "none";
  const bar = document.getElementById("editar-bar");
  bar.style.display = "block";
  bar.innerHTML = "Editando sorteo #" + id + ". Modificá los campos y guarda. <button onclick='guardarEdicion()'>Guardar cambios</button><button class='peligro' onclick='cancelarEdicion()'>Cancelar edicion</button>";
  bar.scrollIntoView({ behavior: "smooth" });
}

function cancelarEdicion() {
  sorteo_edit_id = null;
  document.getElementById("editar-bar").style.display = "none";
  document.getElementById("btn-crear").style.display = "";
  resetImagenForm();
  const ui = document.getElementById("sorteo-imagen"); if (ui) ui.value = "";
  cambiarModalidadSorteo();
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
  delete cuerpo.imagen_data;
  delete cuerpo.detalle;
  delete cuerpo.titulo;
  delete cuerpo.busqueda_inicio_min;
  delete cuerpo.busqueda_intervalo_min;
  delete cuerpo.busqueda_duracion_min;
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
  cambiarModalidadSorteo();
  if (p.modalidad === "rifa") {
    document.getElementById("rifa-premio").value = p.premio_fijo ?? "";
  } else if (p.modalidad === "semanal") {
    document.getElementById("semanal-pozobase").value = p.pozo_base ?? "";
  } else {
    document.getElementById("clasico-pozobase").value = p.pozo_base ?? "";
  }
  if (p.horario) document.getElementById("sorteo-horario").value = p.horario;
  document.getElementById("sorteo-precio").value = p.precio_jugada;
  document.getElementById("sorteo-casa").value = p.casa_pct;
  document.getElementById("sorteo-vend").value = p.vendedor_pct ?? "";
  aviso("Guia cargada. Completa dia, cierre, titulo, imagen y busqueda, y crea el sorteo.");
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
      const premioLinea = s.premio_nombre ? "<div class='chico' style='color:#22c55e'>PREMIO: " + s.premio_nombre + "</div>" : "";
      const celdaNombre = "<td><b>" + (s.titulo || s.modalidad) + "</b>" + (s.titulo ? "<div class='chico'>" + s.modalidad + "</div>" : "") + premioLinea + (s.solo_participantes ? " <span class='chico'>VACANTE</span>" : "") + "</td>";
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
      if (s.estado === "liquidado" && s.requiere_pozo && (!s.ganadores || s.ganadores.length === 0)) {
        html += "<button class='secundario' onclick='pozoVacante(" + s.id + ")'>Pozo vacante</button>";
      }
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
      detalle = "Liquidado.\nGanadoras: jugadas " + d.ganadoras.join(", ") + ".\nPozo pagado: $" + d.pozo_pagado + " ($" + porJugada + " por jugada ganadora)." + (d.premio_nombre ? ("\nPremio: " + d.premio_nombre) : "");
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

// ---------- ADMIN: PAGOS A VENDEDORES ----------
async function cargarPagos() {
  try {
    const vs = await api("/admin/vendedores", "GET");
    const sel = document.getElementById("pago-vendedor");
    sel.innerHTML = "<option value=''>Todos los vendedores</option>" + vs.map(v => "<option value='" + v.id + "'>" + v.nombre + " (" + v.usuario + ")</option>").join("");
  } catch (e) { aviso(e.message, true); }
  cargarLiquidaciones();
}

async function cargarLiquidaciones() {
  const vid = document.getElementById("pago-vendedor").value;
  const caja = document.getElementById("lista-liquidaciones");
  if (!caja) return;
  let ruta = "/admin/liquidaciones";
  if (vid) ruta += "?vendedor_id=" + vid;
  try {
    const ls = await api(ruta, "GET");
    LIQ_CACHE = {};
    ls.forEach(l => { LIQ_CACHE[l.id] = l; });
    if (!ls.length) { caja.innerHTML = "<p class='chico'>No hay liquidaciones todavia. Elegi un vendedor, pone el rango y generá la liquidacion.</p>"; return; }
    let html = "<table><tr><th>#</th><th>Vendedor</th><th>Desde</th><th>Hasta</th><th>Total a pagar</th><th>Estado</th><th>Acciones</th></tr>";
    ls.forEach(l => {
      let estado;
      if (l.pagado_admin && l.cobrado_vendedor) estado = "<span class='ok'>Pagado y cobrado ✔</span>";
      else if (l.pagado_admin) estado = "<span class='warn'>Pagado por vos; esperando confirmacion del vendedor</span>";
      else estado = "<span class='chico'>Pendiente de pago
