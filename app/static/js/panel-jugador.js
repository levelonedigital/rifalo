// ---------- JUGADOR: SORTEOS ----------
async function cargarJSorteos() {
  try {
    const ss = await api("/jugador/sorteos", "GET");
    SORTEOS_ABIERTOS_CACHE["j-sorteo"] = {};
    ss.forEach(s => { SORTEOS_ABIERTOS_CACHE["j-sorteo"][s.id] = s; });
    const elegido = JUGADOR_SORTEO_ELEGIDO ? SORTEOS_ABIERTOS_CACHE["j-sorteo"][JUGADOR_SORTEO_ELEGIDO] : null;
    pintarPozo("pozo-jsorteos", elegido || null);
    let html = "<table><tr><th>#</th><th>Img</th><th>Sorteo</th><th>Horario</th><th>Dia</th><th>Cierre</th><th>Estado</th><th>Precio</th><th>Pozo</th><th></th></tr>";
    ss.forEach(s => {
      const jugando = (s.mis_jugadas && s.mis_jugadas.length) ? "<div class='chico' style='color:#FFC107'>Jugando: " + s.mis_jugadas.map((n, i) => ((i + 1) + ": " + n)).join(" - ") + "</div>" : "";
      const botonPozo = "<button class='secundario' onclick='elegirSorteoJugador(" + s.id + ")'>Ver pozo</button>";
      const botonJugar = s.puedo_jugar ? "<button onclick='jugarSorteo(" + s.id + ")'>Jugar</button>" : "<span class='chico'>no habilitado</span>";
      html += "<tr><td>" + s.id + "</td><td>" + (s.imagen_url ? "<img src='" + s.imagen_url + "' style='width:40px;height:40px;object-fit:cover;border-radius:4px'>" : "-") + "</td><td>" + s.nombre_modalidad + (s.reprogramando ? " (REPROGRAMANDO)" : "") + "<div class='chico'>" + (s.detalle || "") + "</div>" + jugando + "</td><td>" + s.horario + "</td><td>" + fmtFecha(s.fecha) + "</td><td>" + (s.hora_cierre || "sin limite") + "</td><td>" + s.estado + "</td><td>$" + s.precio_jugada + "</td><td><b style='color:#FFC107'>$" + s.pozo + "</b></td><td>" + botonPozo + botonJugar + "</td></tr>";
      html += "<tr id='pozo-fila-" + s.id + "' style='display:none'><td colspan='10'><div class='pozo-grande' style='font-size:16px'>POZO ACTUAL<br><span>$" + s.pozo + "</span><br><small style='font-size:12px;font-weight:normal'>Sorteo #" + s.id + " - " + s.nombre_modalidad + " " + s.horario + " - " + fmtFecha(s.fecha) + "</small></div></td></tr>";
    });
    document.getElementById("lista-jsorteos").innerHTML = html + "</table>";
  } catch (e) { aviso(e.message, true); }
}

function elegirSorteoJugador(id) {
  JUGADOR_SORTEO_ELEGIDO = id;
  document.querySelectorAll("[id^='pozo-fila-']").forEach(f => { f.style.display = "none"; });
  const fila = document.getElementById("pozo-fila-" + id);
  if (fila) {
    fila.style.display = "table-row";
    fila.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  const s = SORTEOS_ABIERTOS_CACHE["j-sorteo"] && SORTEOS_ABIERTOS_CACHE["j-sorteo"][id];
  pintarPozo("pozo-jsorteos", s || null);
  const sel = document.getElementById("j-sorteo");
  if (sel && s) {
    sel.value = String(id);
    pintarReglasSelect("j-sorteo", "j-reglas", "j-imagen");
  }
}

function jugarSorteo(id) {
  JUGADOR_SORTEO_ELEGIDO = id;
  irTab("jcargar");
}

async function jCargarJugada() {
  const cuerpo = {
    sorteo_id: parseInt(document.getElementById("j-sorteo").value),
    numeros: parseNumeros(document.getElementById("j-numeros").value),
  };
  try {
    const d = await api("/jugador/jugadas", "POST", cuerpo);
    aviso("Jugada #" + d.id + " cargada, espera aprobacion de tu vendedor.");
    document.getElementById("j-numeros").value = "";
  }
  catch (e) { aviso(e.message, true); }
}

// ---------- REGISTRO DE PESTANAS DEL JUGADOR ----------
window.ACCIONES = window.ACCIONES || {};
ACCIONES.jsorteos = cargarJSorteos;
ACCIONES.jcargar = async () => {
  await llenarSelectSorteos("/jugador/sorteos", "j-sorteo");
  if (JUGADOR_SORTEO_ELEGIDO && SORTEOS_ABIERTOS_CACHE["j-sorteo"] && SORTEOS_ABIERTOS_CACHE["j-sorteo"][JUGADOR_SORTEO_ELEGIDO]) {
    document.getElementById("j-sorteo").value = String(JUGADOR_SORTEO_ELEGIDO);
    pintarReglasSelect("j-sorteo", "j-reglas", "j-imagen");
  }
};