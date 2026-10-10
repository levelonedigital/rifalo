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

// ---------- AVISO: JUGADAS IGUALES / PREMIO ESTIMADO ----------
function avisoIgualesHTML(info) {
  if (!info || !info.aplica || !(info.coincidencias > 0)) return "";
  const otras = info.coincidencias;
  const total = otras + 1;
  return "<div style='margin:6px 0;padding:8px 10px;border-radius:8px;background:#7c2d12;border:1px solid #f59e0b;color:#fef3c7;font-size:12px'>" +
    "<b>Atención:</b> hay " + otras + " jugada" + (otras === 1 ? "" : "s") + " igual" + (otras === 1 ? "" : "es") + " a esta en el mismo sorteo. " +
    "Si esta combinación gana, el pozo se divide entre " + total + " y tu premio hasta el momento sería <b>$" + info.premio_estimado + "</b>. " +
    "<span class='chico'>(pozo al momento $" + info.pozo_estimado + "; puede crecer con nuevas jugadas)</span></div>";
}

function mostrarAvisoIguales(info) {
  let div = document.getElementById("j-aviso-iguales");
  if (!div) {
    div = document.createElement("div");
    div.id = "j-aviso-iguales";
    const msg = document.getElementById("j-msg");
    if (msg) msg.insertAdjacentElement("afterend", div);
    else {
      const sec = document.getElementById("seccion-jcargar");
      if (sec) sec.appendChild(div);
    }
  }
  div.innerHTML = avisoIgualesHTML(info);
}

function limpiarAvisoIguales() {
  const div = document.getElementById("j-aviso-iguales");
  if (div) div.innerHTML = "";
}

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
    let html = "<table><tr><th>#</th><th>Sorteo</th><th>Horario</th><th>Dia</th><th>Cierre</th><th>Estado</th><th>Precio</th><th>Pozo / Premio</th><th>Cupos</th><th></th></tr>";
    ss.forEach(s => {
      const filaImagen = s.imagen_url
        ? "<tr><td colspan='10' style='padding:10px 4px 2px;text-align:center'>" +
            "<img src='" + s.imagen_url + "' style='display:block;margin:0 auto;max-width:560px;width:100%;height:auto;max-height:320px;object-fit:contain;border-radius:14px;box-shadow:0 6px 18px rgba(0,0,0,.25)'>" +
          "</td></tr>"
        : "";
      let jugando = "";
      if (s.mis_jugadas_info && s.mis_jugadas_info.length) {
        jugando = "<div class='chico' style='color:#FFC107'>Jugando: " + s.mis_jugadas_info.map((j, i) => ((i + 1) + ": " + j.numeros)).join(" - ") + "</div>";
        s.mis_jugadas_info.forEach(j => { jugando += avisoIgualesHTML(j); });
      } else if (s.mis_jugadas && s.mis_jugadas.length) {
        jugando = "<div class='chico' style='color:#FFC107'>Jugando: " + s.mis_jugadas.map((n, i) => ((i + 1) + ": " + n)).join(" - ") + "</div>";
      }
      const cuposTxt = s.cupos_disponibles > 0
        ? "<b style='color:#22c55e'>" + s.cupos_disponibles + " disponible(s)</b>"
        : "<span class='chico' style='color:#ef4444'>Sin cupos</span>";
      const botonPozo = "<button class='secundario' onclick='elegirSorteoJugador(" + s.id + ")'>Ver pozo/Premio</button>";
      const botonJugar = s.puedo_jugar && s.cupos_disponibles > 0
        ? "<button onclick='jugarSorteo(" + s.id + ")'>Jugar</button>"
        : (s.cupos_disponibles === 0 ? "<span class='chico'>Compra cupos a tu vendedor</span>" : "<span class='chico'>no habilitado</span>");
      const celdaPozo = tienePremioNombre(s) ? "<b style='color:#22c55e'>" + s.premio_nombre + "</b>" : "<b style='color:#FFC107'>$" + s.pozo + "</b>";
      html += filaImagen;
      html += "<tr><td>" + s.id + "</td><td><b>" + nombreSorteo(s) + "</b>" + (s.titulo ? "<div class='chico'>" + s.modalidad + "</div>" : "") + (s.reprogramando ? " (REPROGRAMANDO)" : "") + "<div class='chico'>" + (s.detalle || "") + "</div>" + jugando + "</td><td>" + s.horario + "</td><td>" + fmtFecha(s.fecha) + "</td><td>" + (s.hora_cierre || "sin limite") + "</td><td>" + s.estado + "</td><td>$" + s.precio_jugada + "</td><td>" + celdaPozo + "</td><td>" + cuposTxt + "</td><td>" + botonPozo + botonJugar + "</td></tr>";
      html += "<tr id='pozo-fila-" + s.id + "' style='display:none'><td colspan='10'><div class='pozo-grande' style='font-size:16px'>" + cartelSorteoHtml(s) + "</div></td></tr>";
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
}

function jugarSorteo(id) {
  JUGADOR_SORTEO_ELEGIDO = id;
  const sel = document.getElementById("j-sorteo");
  if (sel) {
    sel.value = String(id);
    pintarReglasSelect("j-sorteo", "j-reglas", "j-imagen");
  }
  irTab("jcargar");
}

async function jCargarJugada() {
  const cuerpo = {
    sorteo_id: parseInt(document.getElementById("j-sorteo").value),
    numeros: parseNumeros(document.getElementById("j-numeros").value),
  };
  try {
    const d = await api("/jugador/jugadas", "POST", cuerpo);
    mostrarMsgJugada("Jugada #" + d.id + " completada con exito. Ya estas participando del sorteo.", false);
    mostrarAvisoIguales(d.aviso_iguales);
    document.getElementById("j-numeros").value = "";
    // Refrescar la lista de sorteos para actualizar los cupos disponibles
    cargarJSorteos();
  }
  catch (e) { mostrarMsgJugada(e.message, true); limpiarAvisoIguales(); }
}

// ---------- JUGADOR: RESULTADOS Y COBRO ----------

async function cargarResultadosJugador() {
    const caja = document.getElementById("lista-resultados-jugador");
    if (!caja) return;
    try {
        const rs = await api("/jugador/resultados", "GET");
        if (!rs.length) {
            caja.innerHTML = "<p class='chico'>Todavia no hay sorteos liquidados.</p>";
            return;
        }
        let html = "";
        rs.forEach(r => {
            html += "<div class='buscador-box'>";
            html += "<b>Sorteo #"+r.sorteo_id+"</b> - "+(r.titulo||r.modalidad)+" "+r.horario+" - "+fmtFecha(r.fecha)+"<br>";
            html += resultadosColumnaHTML(r.resultados);
            html += "<span class='chico'>Cantidad de ganadores: "+r.cantidad_ganadores+"</span><br>";
            if (r.mis_jugadas && r.mis_jugadas.length) {
                r.mis_jugadas.forEach(j => {
                    if (j.estado==="ganadora") {
                        const premioTxt = r.premio_nombre ? ("GANASTE: "+r.premio_nombre) : ("GANASTE $"+j.premio);
                        html += "<div class='cobro-box'><b>"+premioTxt+"</b> con la jugada #"+j.id+" ("+j.numeros+").<br>";
                        html += (j.premio_pagado ? "Tu vendedor marco el premio como entregado. " : "Premio pendiente de entrega. ");
                        if (j.premio_cobrado) {
                            html += "<b>Cobrado ✔</b>";
                        } else {
                            html += "<button onclick='confirmarCobroJugador("+j.id+")'>Confirmar que cobre</button>";
                        }
                        html += "<br><span class='chico'>Comunicate con tu vendedor asi te entrega el premio.</span></div>";
                    } else {
                        html += "<div class='chico'>Tu jugada #"+j.id+" ("+j.numeros+"): "+j.estado+".</div>";
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
        await api("/jugador/jugadas/"+jugadaId+"/confirmar-cobro","POST");
        aviso("Gracias, confirmaste el cobro de tu premio.");
        cargarResultadosJugador();
    } catch (e) { aviso(e.message, true); }
}

// ---------- REGISTRO DE PESTANAS DEL JUGADOR ----------
window.ACCIONES = window.ACCIONES || {};
ACCIONES.jsorteos = cargarJSorteos;
ACCIONES.jcargar = async () => {
  limpiarMsgJugada();
  limpiarAvisoIguales();
  await llenarSelectSorteos("/jugador/sorteos", "j-sorteo");
  if (JUGADOR_SORTEO_ELEGIDO && SORTEOS_ABIERTOS_CACHE["j-sorteo"] && SORTEOS_ABIERTOS_CACHE["j-sorteo"][JUGADOR_SORTEO_ELEGIDO]) {
    document.getElementById("j-sorteo").value = String(JUGADOR_SORTEO_ELEGIDO);
    pintarReglasSelect("j-sorteo", "j-reglas", "j-imagen");
  }
};
ACCIONES.resultados = cargarResultadosJugador;
