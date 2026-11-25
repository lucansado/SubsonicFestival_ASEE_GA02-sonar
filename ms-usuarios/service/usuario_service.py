# ms-usuarios/service/usuario_service.py
# Lógica de negocio de perfiles, administración de usuarios, proveedores y preferencias
from datetime import date, datetime, timezone
from sqlalchemy.orm import Session
from config.errores import ErrorApi
from config.seguridad import Identidad
from eventos.publicador import publicar
from model.dto.usuario_dto import (
    CambioUsuarioAdminDTO, DispositivoEntradaDTO, PerfilCambioDTO, PreferenciasNotificacionDTO, RegistroEntradaDTO,
    Rol,
)
from model.factory.factory_dao import DAOFactory
from model.models import Proveedor, Usuario
from service import firebase_auth

usuario_dao = DAOFactory.get_usuario_dao()
entrada_dao = DAOFactory.get_entrada_dao()


def _publicar_proveedor(usuario: Usuario) -> None:
    """Alimenta la réplica de proveedores de ms-espacios."""
    if usuario.rol != Rol.PROVEEDOR.value or not usuario.proveedor:
        return
    tipo = "usuarios.proveedor.actualizado" if usuario.activo else "usuarios.proveedor.desactivado"
    publicar(tipo, {
        "proveedor_id": usuario.id, "nombre_comercial": usuario.proveedor.nombre_comercial,
        "tipo_servicio": usuario.proveedor.tipo_servicio, "validado": usuario.proveedor.validado,
        "activo": usuario.activo,
    })


# ── Perfil propio ───────────────────────────────────────────

def registrar(db: Session, identidad: Identidad, datos: RegistroEntradaDTO) -> Usuario:
    if not identidad.email:
        raise ErrorApi(400, "EMAIL_REQUERIDO", "El token no incluye el email (cabecera X-User-Email)")
    if usuario_dao.existe(db, identidad.id):
        raise ErrorApi(409, "PERFIL_EXISTENTE", "El usuario ya tiene perfil")
    if usuario_dao.existe_email(db, identidad.email):
        raise ErrorApi(409, "EMAIL_EXISTENTE", "Ya hay un perfil con ese email")

    usuario = Usuario(id=identidad.id, email=identidad.email, nombre=datos.nombre, apellidos=datos.apellidos,
                      telefono=datos.telefono, direccion=datos.direccion, rol=datos.rol.value, activo=True)
    if datos.rol.value == Rol.PROVEEDOR.value:
        usuario.proveedor = Proveedor(**(datos.proveedor.model_dump() if datos.proveedor else {}), validado=False)
    usuario_dao.crear(db, usuario)
    try:
        firebase_auth.asignar_rol(usuario.id, usuario.rol)
        db.commit()
    except Exception:
        db.rollback()
        raise
    publicar("usuarios.usuario.registrado", {"usuario_id": usuario.id, "rol": usuario.rol})
    _publicar_proveedor(usuario)
    return usuario


def obtener_perfil(db: Session, usuario_id: str) -> Usuario:
    usuario = usuario_dao.obtener(db, usuario_id)
    if not usuario:
        raise ErrorApi(404, "PERFIL_NO_ENCONTRADO", "El usuario todavía no ha registrado su perfil")
    return usuario


def modificar_perfil(db: Session, usuario_id: str, datos: PerfilCambioDTO) -> Usuario:
    usuario = obtener_perfil(db, usuario_id)
    cambios = datos.model_dump(exclude_unset=True, exclude={"proveedor", "activo"})
    for campo, valor in cambios.items():
        setattr(usuario, campo, valor)

    if datos.activo is not None and datos.activo != usuario.activo:
        if datos.activo:
            # Una cuenta desactivada solo la reactiva un administrador
            raise ErrorApi(403, "SIN_PERMISO", "Solo un administrador puede reactivar la cuenta")
        usuario.activo = False

    if datos.proveedor is not None:
        if usuario.rol != Rol.PROVEEDOR.value:
            raise ErrorApi(400, "PETICION_NO_VALIDA", "Solo los proveedores tienen datos de proveedor")
        for campo, valor in datos.proveedor.model_dump(exclude_unset=True).items():
            setattr(usuario.proveedor, campo, valor)

    db.commit()
    _publicar_proveedor(usuario)
    return usuario


def eliminar_cuenta(db: Session, usuario_id: str) -> None:
    usuario = obtener_perfil(db, usuario_id)
    if entrada_dao.tiene_entradas_pendientes(db, usuario_id, date.today()):
        raise ErrorApi(409, "ENTRADAS_ACTIVAS", "Tiene entradas activas de eventos no celebrados; cancélalas antes")

    # RGPD: se borran los datos personales; la fila queda anonimizada para conservar el histórico de entradas
    usuario_dao.borrar_datos_relacionados(db, usuario_id)
    usuario.email = f"{usuario_id}@eliminado.invalid"
    usuario.nombre = usuario.apellidos = usuario.telefono = usuario.direccion = None
    usuario.activo = False
    usuario.eliminado_en = datetime.now(timezone.utc)
    try:
        db.flush()
        firebase_auth.eliminar_cuenta(usuario_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    publicar("usuarios.usuario.eliminado", {"usuario_id": usuario_id})


# ── Administración ──────────────────────────────────────────

def listar_usuarios(db: Session, **filtros):
    return usuario_dao.listar(db, **filtros)


def obtener_usuario(db: Session, usuario_id: str, *, bloquear: bool = False) -> Usuario:
    usuario = usuario_dao.obtener(db, usuario_id, bloquear=bloquear)
    if not usuario:
        raise ErrorApi(404, "USUARIO_NO_ENCONTRADO", f"No existe el usuario {usuario_id}")
    return usuario


def modificar_usuario(db: Session, usuario_id: str, datos: CambioUsuarioAdminDTO) -> Usuario:
    usuario = obtener_usuario(db, usuario_id, bloquear=True)
    if datos.rol is not None and datos.rol.value != usuario.rol:
        usuario.rol = datos.rol.value
        if usuario.rol == Rol.PROVEEDOR.value and not usuario.proveedor:
            usuario.proveedor = Proveedor(validado=False)
        firebase_auth.asignar_rol(usuario.id, usuario.rol)
    if datos.activo is not None:
        usuario.activo = datos.activo
    db.commit()
    _publicar_proveedor(usuario)
    return usuario


def listar_proveedores(db: Session, **filtros):
    return usuario_dao.listar_proveedores(db, **filtros)


def validar_proveedor(db: Session, usuario_id: str, validado: bool) -> Usuario:
    usuario = obtener_usuario(db, usuario_id, bloquear=True)
    if usuario.rol != Rol.PROVEEDOR.value or not usuario.proveedor:
        raise ErrorApi(404, "PROVEEDOR_NO_ENCONTRADO", f"{usuario_id} no es un proveedor")
    usuario.proveedor.validado = validado
    db.commit()
    _publicar_proveedor(usuario)
    return usuario


# ── Notificaciones ──────────────────────────────────────────

def obtener_preferencias(db: Session, usuario_id: str) -> PreferenciasNotificacionDTO:
    obtener_perfil(db, usuario_id)
    preferencias = usuario_dao.obtener_preferencias(db, usuario_id)
    if not preferencias:
        return PreferenciasNotificacionDTO(push=True, email=True)
    return PreferenciasNotificacionDTO.model_validate(preferencias)


def guardar_preferencias(db: Session, usuario_id: str, datos: PreferenciasNotificacionDTO):
    obtener_perfil(db, usuario_id)
    preferencias = usuario_dao.obtener_o_crear_preferencias(db, usuario_id)
    preferencias.push = datos.push
    preferencias.email = datos.email
    db.commit()
    return PreferenciasNotificacionDTO.model_validate(preferencias)


def registrar_dispositivo(db: Session, usuario_id: str, datos: DispositivoEntradaDTO) -> None:
    obtener_perfil(db, usuario_id)
    preferencias = usuario_dao.obtener_o_crear_preferencias(db, usuario_id)
    if datos.fcm_token not in preferencias.fcm_tokens:
        # Se reasigna la lista para que SQLAlchemy detecte el cambio en la columna JSON
        preferencias.fcm_tokens = [*preferencias.fcm_tokens, datos.fcm_token]
    db.commit()


def eliminar_dispositivo(db: Session, usuario_id: str, fcm_token: str) -> None:
    preferencias = usuario_dao.obtener_preferencias(db, usuario_id)
    if preferencias is None:
        return
    # Reasignar la lista permite persistir el cambio en la columna JSON/JSONB.
    preferencias.fcm_tokens = [t for t in preferencias.fcm_tokens if t != fcm_token]
    db.commit()
