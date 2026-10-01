// ---------- MENSAJE LOCAL (debajo del boton Cargar) ----------
function mostrarMsgJugada(texto, err) {
  let div = document.getElementById("j-msg");
  if (!div) {
    div = document.createElement("div");
    div.id = "j-msg";
    const boton = document.querySelector('#seccion-jcargar button[onclick*="jCargarJugada"]');
    if (boton) boton.insertAdjacentElement("afterend", div);
    else {
      const sec = document.getElementById("seccion-jcargar");
      if (sec) sec.appendChild(div);
    }
  }
  div.className = "mensaje " + (err ? "error" : "ok");
  div.textContent = texto || "";
}

function limpiarMsgJugada() { mostrarMsgJugada("", false); }

// ---------- JUGADOR: SORTEOS ----------
async function cargarJSorteos() {
  try {
    const ss = await api("/jugador/sorteos", "GET");
    SORTEOS_ABIERTOS_CACHE["j-sorteo"] = {};
    ss.forEach(s => { SORTEOS_ABIERTOS_CACHE["j-sorteo"][s.id] = s; });
    const elegido = JUGADOR_SORTEO_ELEGIDO ? SORTEOS_ABIERTOS_CACHE["j-sorteo"][JUGADOR_SORTEO_ELEGIDO] : null;
    const cartel = document.getElementById("pozo-jsorteos");
    if (cartel) {
      cartel.style.display = "block";
      cartel.innerHTML = cartelSorteoHtml(elegido);
    }
    let html = "<table><tr><th>#</th><th>Sorteo</th><th>Horario</th><th>Dia</th><th>Cierre</th><th>Estado</th><th>Precio</th><th>Pozo / Premio</th><th></th></tr>";
    ss.forEach(s => {
      // Banner de imagen: centrado, sin fondo, arriba del detalle del sorteo.
      const filaImagen = s.imagen_url
        ? "<tr><td colspan='9' style='padding:10px 4px 2px;text-align:center'>" +
            "<img src='" + s.imagen_url + "' style='display:block;margin:0 auto;max-width:560px;width:100%;height:auto;max-height:320px;object-fit:contain;border-radius:14px;box-shadow:0 6px 18px rgba(0,0,0,.25)'>" +
          "</td></tr>"
        : "";
      const jugando = (s.mis_jugadas && s.mis_jugadas.length) ? "<div class='chico' style='color:#FFC107'>Jugando: " + s.mis_jugadas.map((n, i) => ((i + 1) + ": " + n)).join(" - ") + "</div>" : "";
      const botonPozo = "<button class='secundario' onclick='elegirSorteoJugador(" + s.id + ")'>Ver pozo/Premio</button>";
      const botonJugar = s.puedo_jugar ? "<button onclick='jugarSorteo(" + s.id + ")'>Jugar</button>" : "<span class='chico'>no habilitado</span>";
      const celdaPozo = tienePremioNombre(s) ? "<b style='color:#22c55e'>" + s.premio_nombre + "</b>" : "<b style='color:#FFC107'>$" + s.pozo + "</b>";
      html += filaImagen;
      html += "<tr><td>" + s.id + "</td><td><b>" + nombreSorteo(s) + "</b>" + (s.titulo ? "<div class='chico'>" + s.modalidad + "</div>" : "") + (s.reprogramando ? " (REPROGRAMANDO)" : "") + "<div class='chico'>" + (s.detalle || "") + "</div>" + jugando + "</td><td>" + s.horario + "</td><td>" + fmtFecha(s.fecha) + "</td><td>" + (s.hora_cierre || "sin limite") + "</td><td>" + s.estado + "</td><td>$" + s.precio_jugada + "</td><td>" + celdaPozo + "</td><td>" + botonPozo + botonJugar + "</td></tr>";
      html += "<tr id='pozo-fila-" + s.id + "' style='display:none'><td colspan='9'><div class='pozo-grande' style='font-size:16px'>" + cartelSorteoHtml(s) + "</div></td></tr>";
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
  const cartel = document.getElementById("pozo-jsorteos");
  if (cartel) {
    cartel.style.display = "block";
    cartel.innerHTML = cartelSorteoHtml(s);
  }
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
    mostrarMsgJugada("Jugada #" + d.id + " cargada, espera aprobación de tu vendedor.", false);
    document.getElementById("j-numeros").value = "";
  }
  catch (e) { mostrarMsgJugada(e.message, true); }
}

// ---------- JUGADOR: RESULTADOS Y COBRO ----------
async function cargarResultadosJugador() {
  const caja = document.getElementById("lista-resultados-jugador");
  if (!caja) return;
  try {
    const rs = await api("/jugador/resultados", "GET");
    if (!rs.length) { caja.innerHTML = "<p class='chico'>Todavia no hay sorteos liquidados.</p>"; return; }
    let html = "";
    rs.forEach(r => {
      html += "<div class='buscador-box'>";
      html += "<b>Sorteo #" + r.sorteo_id + "</b> - " + (r.titulo || r.modalidad) + " " + r.horario + " - " + fmtFecha(r.fecha) + "<br>";
      html += "<span class='nums'>Numeros: " + r.resultados.map(n => String(n).padStart(2, "0")).join(", ") + "</span><br>";
      html += "<span class='chico'>Cantidad de ganadores: " + r.cantidad_ganadores + "</span><br>";
      if (r.mis_jugadas && r.mis_jugadas.length) {
        r.mis_jugadas.forEach(j => {
          if (j.estado === "ganadora") {
            const premioTxt = r.premio_nombre ? ("GANASTE: " + r.premio_nombre) : ("GANASTE $" + j.premio);
            html += "<div class='cobro-box'><b>" + premioTxt + "</b> con la jugada #" + j.id + " (" + j.numeros + ").<br>";
            html += (j.premio_pagado ? "Tu vendedor marco el premio como entregado. " : "Premio pendiente de entrega. ");
            if (j.premio_cobrado) {
              html += "<b>Cobrado ✔</b>";
            } else {
              html += "<button onclick='confirmarCobroJugador(" + j.id + ")'>Confirmar que cobre</button>";
            }
            html += "<br><span class='chico'>Comunicate con tu vendedor asi te entrega el premio.</span></div>";
          } else {
            html += "<div class='chico'>Tu jugada #" + j.id + " (" + j.numeros + "): " + j.estado + ".</div>";
          }
        });
      } else {
        html += "<span class='chico'>No participaste de este sorteo.</span>";
      }
      html += "</div>";
    });
    caja.innerHTML = html;
  } catch (e) { aviso(e.message, true); }
}

async function confirmarCobroJugador(jugadaId) {
  if (!confirm("Confirma que ya cobraste este premio?")) return;
  try {
    await api("/jugador/jugadas/" + jugadaId + "/confirmar-cobro", "POST");
    aviso("Gracias, confirmaste el cobro de tu premio.");
    cargarResultadosJugador();
  } catch (e) { aviso(e.message, true); }
}

// ---------- REGISTRO DE PESTANAS DEL JUGADOR ----------
window.ACCIONES = window.ACCIONES || {};
ACCIONES.jsorteos = cargarJSorteos;
ACCIONES.jcargar = async () => {
  limpiarMsgJugada();
  await llenarSelectSorteos("/jugador/sorteos", "j-sorteo");
  if (JUGADOR_SORTEO_ELEGIDO && SORTEOS_ABIERTOS_CACHE["j-sorteo"] && SORTEOS_ABIERTOS_CACHE["j-sorteo"][JUGADOR_SORTEO_ELEGIDO]) {
    document.getElementById("j-sorteo").value = String(JUGADOR_SORTEO_ELEGIDO);
    pintarReglasSelect("j-sorteo", "j-reglas", "j-imagen");
  }
};
