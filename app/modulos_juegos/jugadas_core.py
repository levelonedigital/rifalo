from app.core import auditoria
from app.modelos.juegos import EstadoSorteo, Jugada, ModuloJuego, Sorteo
from app.modelos.usuario import Usuario

CANTIDADES = {ModuloJuego.CLASICO: 3, ModuloJuego.SEMANAL: 10, ModuloJuego.RIFA: 1}


def precio_de(sorteo: Sorteo, reglas) -> float:
    """Precio de la jugada: el del sorteo si esta configurado, si no el de las reglas."""
    if sorteo.precio_jugada is not None:
        return sorteo.precio_jugada
    return {
        ModuloJuego.CLASICO: reglas.precio_clasico,
        ModuloJuego.SEMANAL: reglas.precio_semanal,
        ModuloJuego.RIFA: reglas.precio_rifa,
    }[sorteo.modulo]


def validar_numeros(modulo: ModuloJuego, numeros) -> str | None:
    cantidad = CANTIDADES.get(modulo)
    if cantidad is None:
        return "Modulo invalido"
    if len(numeros) != cantidad:
        return f"El modulo {modulo.value} requiere exactamente {cantidad} numeros"
    for n in numeros:
        if not isinstance(n, int) or n < 0 or n > 99:
            return "Los numeros deben estar entre 0 y 99"
    if len(set(numeros)) != len(numeros):
        return "La jugada tiene numeros repetidos"
    return None


def crear_jugada(
    sesion,
    sorteo: Sorteo,
    numeros,
    vendedor_dueno: Usuario,
    reglas,
    revendedor_id=None,
    jugador_id=None,
    jugador_nombre=None,
) -> Jugada:
    """Valida y crea una jugada pendiente. Lanza ValueError con el motivo si no pasa."""
    if sorteo.estado != EstadoSorteo.PROGRAMADO:
        raise ValueError("El sorteo no esta abierto para cargar jugadas")
    error = validar_numeros(sorteo.modulo, numeros)
    if error:
        raise ValueError(error)
    if sorteo.solo_participantes:
        habilitados = {p.strip().lower() for p in (sorteo.participantes or "").split("|") if p.strip()}
        nombre = (jugador_nombre or "").strip().lower()
        if nombre not in habilitados:
            raise ValueError("Sorteo de pozo vacante: solo pueden jugar quienes participaron del original")
    jugada = Jugada(
        sorteo_id=sorteo.id,
        vendedor_id=vendedor_dueno.id,
        revendedor_id=revendedor_id,
        jugador_id=jugador_id,
        jugador_nombre=jugador_nombre,
        numeros=",".join(f"{n:02d}" for n in numeros),
        precio=precio_de(sorteo, reglas),
    )
    sesion.add(jugada)
    sesion.commit()
    sesion.refresh(jugada)
    auditoria.registrar(
        sesion,
        "JUGADA_CARGADA",
        detalle=f"sorteo={sorteo.id} numeros={jugada.numeros} precio={jugada.precio}",
        usuario=vendedor_dueno,
    )
    sesion.commit()
    return jugada
