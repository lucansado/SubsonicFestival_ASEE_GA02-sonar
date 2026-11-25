# ms-usuarios/service/entrada_service.py
# Lógica de negocio de entradas (compra, cancelación, validación) y artistas favoritos
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID
from sqlalchemy.orm import Session
from config.errores import ErrorApi
from eventos.publicador import publicar
from model.dto.entrada_dto import (
    CompraEntradaDTO, EstadoEntrada, ResolucionCancelacion, ValidacionDTO,
)
from model.factory.factory_dao import DAOFactory
from model.models import ArtistaFavorito, Entrada
from service import clientes, pasarela_pago, qr
from service.notificaciones import notificar

usuario_dao = DAOFactory.get_usuario_dao()
entrada_dao = DAOFactory.get_entrada_dao()

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre",
         "Noviembre", "Diciembre"]


def texto_fechas(inicio: date, fin: date) -> str:
    """2026-07-18 / 2026-07-27 -> «18 – 27 Julio 2026» (formato de la versión actual)."""
    if inicio.month == fin.month and inicio.year == fin.year:
        return f"{inicio.day} – {fin.day} {MESES[fin.month - 1]} {fin.year}"
    return f"{inicio.day} {MESES[inicio.month - 1]} – {fin.day} {MESES[fin.month - 1]} {fin.year}"


def _datos_entrada(entrada: Entrada) -> dict:
    return {"entrada_id": entrada.id, "usuario_id": entrada.usuario_id, "evento_id": entrada.evento_id,
            "tipo_pase": entrada.tipo_pase, "precio_pagado": float(entrada.precio_pagado),
            "reserva_id": str(entrada.reserva_id) if entrada.reserva_id else None, "estado": entrada.estado}


# ── Compra ──────────────────────────────────────────────────

def comprar(db: Session, usuario_id: str, datos: CompraEntradaDTO) -> Entrada:
    usuario = usuario_dao.obtener(db, usuario_id)
    if not usuario or not usuario.activo:
        raise ErrorApi(403, "SIN_PERMISO", "Solo los clientes con cuenta activa pueden comprar")

    # 1. Reserva de aforo en ms-espacios (409 sin cupo, 404 evento, 503 si no responde)
    reserva = clientes.reservar_aforo(datos.evento_id, datos.tipo_pase.value, usuario_id)
    precio = Decimal(str(reserva["precio"]))

    # 2. Cobro; si falla se libera la reserva
    try:
        pago_ref = pasarela_pago.cobrar(datos.token_pago, precio)
    except pasarela_pago.PagoRechazado as e:
        clientes.liberar_aforo(reserva["reserva_id"])
        raise ErrorApi(402, "PAGO_RECHAZADO", str(e))

    # 3. Entrada con QR firmado
    entrada_id = f"entrada-{uuid.uuid4().hex[:8]}"
    inicio, fin = date.fromisoformat(reserva["fecha_inicio"]), date.fromisoformat(reserva["fecha_fin"])
    entrada = entrada_dao.crear(db, Entrada(
        id=entrada_id, usuario_id=usuario_id, evento_id=datos.evento_id,
        evento_titulo=reserva["evento_titulo"], evento_fechas=texto_fechas(inicio, fin),
        evento_fecha_inicio=inicio, evento_fecha_fin=fin, tipo_pase=datos.tipo_pase.value,
        precio_pagado=precio, estado=EstadoEntrada.ACTIVA.value, codigo_qr=qr.generar(entrada_id, datos.evento_id),
        reserva_id=UUID(reserva["reserva_id"]), pago_ref=pago_ref,
    ))
    db.commit()

    # 4. ms-espacios confirma la reserva al recibir este evento
    publicar("usuarios.entrada.comprada", _datos_entrada(entrada))
    return entrada


# ── Consulta y cancelación ──────────────────────────────────

def mis_entradas(db: Session, usuario_id: str, estado: EstadoEntrada | None) -> list[Entrada]:
    return entrada_dao.listar_de_usuario(db, usuario_id, estado.value if estado else None)


def mi_entrada(db: Session, usuario_id: str, entrada_id: str, *, bloquear: bool = False) -> Entrada:
    entrada = entrada_dao.obtener(db, entrada_id, bloquear=bloquear)
    # Una entrada ajena se responde como inexistente para no revelar su existencia
    if not entrada or entrada.usuario_id != usuario_id:
        raise ErrorApi(404, "ENTRADA_NO_ENCONTRADA", f"No existe la entrada {entrada_id}")
    return entrada


def solicitar_cancelacion(db: Session, usuario_id: str, entrada_id: str, motivo: str) -> Entrada:
    entrada = mi_entrada(db, usuario_id, entrada_id, bloquear=True)
    if entrada.estado != EstadoEntrada.ACTIVA.value:
        raise ErrorApi(409, "ENTRADA_NO_ACTIVA", f"La entrada está {entrada.estado}")
    if entrada.evento_fecha_inicio and entrada.evento_fecha_inicio <= date.today():
        raise ErrorApi(409, "EVENTO_INICIADO", "El evento ya ha empezado")
    entrada.estado = EstadoEntrada.CANCELACION_SOLICITADA.value
    entrada.motivo_cancelacion = motivo
    db.commit()
    return entrada


def listar_entradas(db: Session, **filtros):
    return entrada_dao.listar(db, **filtros)


def _cancelar(entrada: Entrada, motivo: str | None = None) -> None:
    pasarela_pago.reembolsar(entrada.pago_ref, entrada.precio_pagado)
    entrada.estado = EstadoEntrada.CANCELADA.value
    if motivo:
        entrada.motivo_cancelacion = motivo


def resolver_cancelacion(db: Session, entrada_id: str, resolucion: ResolucionCancelacion) -> Entrada:
    entrada = entrada_dao.obtener(db, entrada_id, bloquear=True)
    if not entrada:
        raise ErrorApi(404, "ENTRADA_NO_ENCONTRADA", f"No existe la entrada {entrada_id}")
    if entrada.estado != EstadoEntrada.CANCELACION_SOLICITADA.value:
        raise ErrorApi(409, "SIN_SOLICITUD", "La entrada no tiene una solicitud de cancelación pendiente")
    if resolucion == ResolucionCancelacion.CANCELADA:
        _cancelar(entrada)
    else:
        entrada.estado = EstadoEntrada.ACTIVA.value
    db.commit()
    if resolucion == ResolucionCancelacion.CANCELADA:
        publicar("usuarios.entrada.cancelada", _datos_entrada(entrada))
    return entrada


# ── Validación en la puerta ─────────────────────────────────

def validar(db: Session, codigo_qr: str, evento_id: str) -> ValidacionDTO:
    leido = qr.verificar(codigo_qr)
    if not leido:
        raise ErrorApi(400, "QR_NO_VALIDO", "QR ilegible o con firma no válida")
    entrada_id, evento_qr = leido

    entrada = entrada_dao.obtener(db, entrada_id, bloquear=True)
    if not entrada:
        raise ErrorApi(404, "ENTRADA_NO_ENCONTRADA", f"No existe la entrada {entrada_id}")
    if evento_qr != evento_id or entrada.evento_id != evento_id:
        raise ErrorApi(409, "OTRO_EVENTO", "La entrada es de otro evento; acceso denegado")
    if entrada.estado == EstadoEntrada.USADA.value:
        raise ErrorApi(409, "ENTRADA_USADA", "La entrada ya se ha usado; acceso denegado",
                       {"usada_en": entrada.usada_en})
    if entrada.estado != EstadoEntrada.ACTIVA.value:
        raise ErrorApi(409, "ENTRADA_NO_ACTIVA", f"La entrada está {entrada.estado}; acceso denegado")

    entrada.estado = EstadoEntrada.USADA.value
    entrada.usada_en = datetime.now(timezone.utc)
    db.commit()
    publicar("usuarios.entrada.validada", _datos_entrada(entrada))

    titular = " ".join(p for p in (entrada.usuario.nombre, entrada.usuario.apellidos) if p) or entrada.usuario_id
    return ValidacionDTO(entrada_id=entrada.id, tipo_pase=entrada.tipo_pase, titular=titular,
                         validada_en=entrada.usada_en)


# ── Favoritos ───────────────────────────────────────────────

def listar_favoritos(db: Session, usuario_id: str):
    return entrada_dao.listar_favoritos(db, usuario_id)


def anadir_favorito(db: Session, usuario_id: str, artista_id: UUID) -> ArtistaFavorito:
    if not usuario_dao.obtener(db, usuario_id):
        raise ErrorApi(403, "SIN_PERMISO", "El usuario no ha registrado su perfil")
    if entrada_dao.obtener_favorito(db, usuario_id, artista_id):
        raise ErrorApi(409, "FAVORITO_EXISTENTE", "El artista ya está en favoritos")
    nombre = clientes.nombre_artista(str(artista_id))
    favorito = entrada_dao.crear_favorito(db, ArtistaFavorito(usuario_id=usuario_id, artista_id=artista_id,
                                                               artista_nombre=nombre))
    db.commit()
    publicar("usuarios.favorito.anadido", {"usuario_id": usuario_id, "artista_id": str(artista_id),
                                           "artista_nombre": nombre})
    return favorito


def quitar_favorito(db: Session, usuario_id: str, artista_id: UUID) -> None:
    favorito = entrada_dao.obtener_favorito(db, usuario_id, artista_id)
    if not favorito:
        raise ErrorApi(404, "FAVORITO_NO_ENCONTRADO", "El artista no está en favoritos")
    db.delete(favorito)
    db.commit()
    publicar("usuarios.favorito.eliminado", {"usuario_id": usuario_id, "artista_id": str(artista_id)})


# ── Reacciones a eventos de otros servicios (transacción del manejador) ──

def al_cancelar_evento(db: Session, evento_id: str, motivo: str | None = None) -> int:
    """espacios.evento.cancelado: cancela y reembolsa las entradas y avisa a los compradores."""
    entradas = entrada_dao.entradas_activas_de_evento(db, evento_id)
    for entrada in entradas:
        _cancelar(entrada, f"Evento cancelado: {motivo}" if motivo else "Evento cancelado")
    db.flush()
    for entrada in entradas:
        publicar("usuarios.entrada.cancelada", _datos_entrada(entrada))
    notificar(db, {e.usuario_id for e in entradas}, "Evento cancelado",
              f"El evento {evento_id} se ha cancelado; te reembolsaremos la entrada")
    return len(entradas)


def al_modificar_pase(db: Session, datos: dict, *, cancelado: bool = False) -> None:
    """escaleta.pase.modificado / cancelado: push a quien tiene el artista en favoritos y entrada."""
    interesados = entrada_dao.usuarios_con_favorito(db, UUID(datos["artista_id"])) & \
        entrada_dao.usuarios_con_entrada(db, datos["evento_id"])
    artista = datos.get("artista_nombre", "tu artista")
    if cancelado:
        notificar(db, interesados, f"Actuación cancelada: {artista}",
                  datos.get("motivo") or "Consulta la escaleta actualizada", canales=("push",))
    else:
        notificar(db, interesados, f"Cambio en el horario de {artista}",
                  f"Nuevo horario: {datos.get('inicio_nuevo', 'consulta la escaleta')}", canales=("push",))


def al_actualizar_artista(db: Session, artista_id: UUID, nombre: str) -> None:
    """escaleta.artista.actualizado: actualiza el nombre copiado en los favoritos."""
    entrada_dao.renombrar_artista(db, artista_id, nombre)
    db.flush()
