"""Avisos provocados por escaleta, espacios y tienda, sin acceder a sus bases de datos."""
from sqlalchemy.orm import Session
from model.factory.factory_dao import DAOFactory
from service.notificaciones import notificar

usuario_dao = DAOFactory.get_usuario_dao()
entrada_dao = DAOFactory.get_entrada_dao()


def al_publicar_escaleta(db: Session, datos: dict) -> None:
    evento_id = datos["evento_id"]
    notificar(db, entrada_dao.usuarios_con_entrada(db, evento_id), "Escaleta publicada",
              f"Ya puedes consultar la escaleta del evento {evento_id}", canales=("push",))


def al_solicitar_alquiler(db: Session, datos: dict) -> None:
    notificar(db, usuario_dao.administradores_activos(db), "Nueva solicitud de alquiler",
              f"El proveedor {datos['proveedor_id']} solicita el alquiler {datos['alquiler_id']} "
              f"del espacio {datos['espacio_id']}")


def al_resolver_alquiler(db: Session, datos: dict, *, aprobado: bool) -> None:
    estado = "aprobado" if aprobado else "rechazado"
    notificar(db, {datos["proveedor_id"]}, f"Alquiler {estado}",
              f"Tu alquiler {datos['alquiler_id']} del espacio {datos['espacio_id']} ha sido {estado}")


def al_crear_pedido(db: Session, datos: dict) -> None:
    notificar(db, {datos["usuario_id"]}, "Pedido confirmado",
              f"Hemos recibido tu pedido {datos['pedido_id']}. Total: {datos['importe_total']} EUR",
              canales=("email",))


def al_actualizar_pedido(db: Session, datos: dict) -> None:
    mensajes = {
        "PREPARADO": "Tu pedido está preparado",
        "ENVIADO": "Tu pedido está en camino",
        "LISTO_RECOGIDA": "Tu pedido está listo para recoger",
        "ENTREGADO": "Tu pedido ha sido entregado",
        "CANCELADO": "Tu pedido ha sido cancelado",
    }
    estado = datos["estado"]
    titulo = mensajes.get(estado, "Pedido actualizado")
    cuerpo = f"Pedido {datos['pedido_id']}: {estado}"
    if estado == "LISTO_RECOGIDA":
        cuerpo += f". Recógelo en el evento {datos['evento_id_recogida']}"
    notificar(db, {datos["usuario_id"]}, titulo, cuerpo, canales=("email",))


def al_bajar_stock(db: Session, datos: dict) -> None:
    notificar(db, usuario_dao.administradores_activos(db), "Stock bajo",
              f"Producto {datos['producto_id']}, talla {datos['talla']}: "
              f"quedan {datos['stock']} unidades (umbral: {datos['umbral']})")
