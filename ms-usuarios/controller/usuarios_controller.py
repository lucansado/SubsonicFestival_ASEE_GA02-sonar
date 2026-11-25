# ms-usuarios/controller/usuarios_controller.py
# Endpoints de perfil, administración de usuarios, proveedores y notificaciones
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session
from config.database import get_db
from config.seguridad import Identidad, UsuarioActual, autenticado, requiere_rol
from model.dto.usuario_dto import (
    CambioUsuarioAdminDTO, DispositivoEntradaDTO, PerfilCambioDTO, PreferenciasNotificacionDTO, RegistroEntradaDTO,
    Rol, UsuarioDTO, ValidacionProveedorDTO,
)
from service import usuario_service

router = APIRouter()
SOLO_ADMIN = Depends(requiere_rol("admin"))


# ── Perfil ──────────────────────────────────────────────────

@router.post("/usuarios", response_model=UsuarioDTO, status_code=status.HTTP_201_CREATED, tags=["Perfil"],
             summary="Registrar el perfil de un usuario")
def registrar_usuario(datos: RegistroEntradaDTO, response: Response, identidad: Identidad = Depends(autenticado),
                      db: Session = Depends(get_db)):
    usuario = usuario_service.registrar(db, identidad, datos)
    response.headers["Location"] = "/api/v1/usuarios/me"
    return usuario


@router.get("/usuarios/me", response_model=UsuarioDTO, tags=["Perfil"], summary="Obtener el perfil propio")
def obtener_perfil(identidad: Identidad = Depends(autenticado), db: Session = Depends(get_db)):
    return usuario_service.obtener_perfil(db, identidad.id)


@router.patch("/usuarios/me", response_model=UsuarioDTO, tags=["Perfil"],
              summary="Modificar el perfil propio o desactivar la cuenta")
def modificar_perfil(datos: PerfilCambioDTO, identidad: Identidad = Depends(autenticado),
                     db: Session = Depends(get_db)):
    return usuario_service.modificar_perfil(db, identidad.id, datos)


@router.delete("/usuarios/me", status_code=status.HTTP_204_NO_CONTENT, tags=["Perfil"], summary="Eliminar la cuenta")
def eliminar_cuenta(identidad: Identidad = Depends(autenticado), db: Session = Depends(get_db)):
    usuario_service.eliminar_cuenta(db, identidad.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Notificaciones ──────────────────────────────────────────

@router.get("/usuarios/me/preferencias-notificacion", response_model=PreferenciasNotificacionDTO,
            tags=["Notificaciones"], summary="Obtener las preferencias de notificación")
def obtener_preferencias(identidad: Identidad = Depends(autenticado), db: Session = Depends(get_db)):
    return usuario_service.obtener_preferencias(db, identidad.id)


@router.put("/usuarios/me/preferencias-notificacion", response_model=PreferenciasNotificacionDTO,
            tags=["Notificaciones"], summary="Guardar las preferencias de notificación")
def guardar_preferencias(datos: PreferenciasNotificacionDTO, identidad: Identidad = Depends(autenticado),
                         db: Session = Depends(get_db)):
    return usuario_service.guardar_preferencias(db, identidad.id, datos)


@router.post("/usuarios/me/dispositivos", status_code=status.HTTP_201_CREATED, tags=["Notificaciones"],
             summary="Registrar un dispositivo para notificaciones push")
def registrar_dispositivo(datos: DispositivoEntradaDTO, identidad: Identidad = Depends(autenticado),
                          db: Session = Depends(get_db)):
    usuario_service.registrar_dispositivo(db, identidad.id, datos)
    return Response(status_code=status.HTTP_201_CREATED)


@router.delete("/usuarios/me/dispositivos/{fcm_token}", status_code=status.HTTP_204_NO_CONTENT,
               tags=["Notificaciones"], summary="Dar de baja un dispositivo", operation_id="eliminarDispositivo")
def eliminar_dispositivo(fcm_token: str, identidad: Identidad = Depends(autenticado),
                         db: Session = Depends(get_db)):
    usuario_service.eliminar_dispositivo(db, identidad.id, fcm_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Administración de usuarios ──────────────────────────────

@router.get("/usuarios", response_model=list[UsuarioDTO], tags=["Administración de usuarios"],
            summary="Listar usuarios")
def listar_usuarios(
    response: Response,
    rol: Rol | None = Query(default=None),
    activo: bool | None = Query(default=None),
    q: str | None = Query(default=None, description="Búsqueda por nombre o email"),
    limite: int = Query(default=20, ge=1, le=100),
    desplazamiento: int = Query(default=0, ge=0),
    _: UsuarioActual = SOLO_ADMIN,
    db: Session = Depends(get_db),
):
    usuarios, total = usuario_service.listar_usuarios(db, rol=rol.value if rol else None, activo=activo, q=q,
                                                      limite=limite, desplazamiento=desplazamiento)
    response.headers["X-Total-Count"] = str(total)
    return usuarios


@router.get("/usuarios/{usuario_id}", response_model=UsuarioDTO, tags=["Administración de usuarios"],
            summary="Obtener un usuario")
def obtener_usuario(usuario_id: str, _: UsuarioActual = SOLO_ADMIN, db: Session = Depends(get_db)):
    return usuario_service.obtener_usuario(db, usuario_id)


@router.patch("/usuarios/{usuario_id}", response_model=UsuarioDTO, tags=["Administración de usuarios"],
              summary="Cambiar el rol o activar/desactivar un usuario")
def modificar_usuario(usuario_id: str, datos: CambioUsuarioAdminDTO, _: UsuarioActual = SOLO_ADMIN,
                      db: Session = Depends(get_db)):
    return usuario_service.modificar_usuario(db, usuario_id, datos)


@router.get("/proveedores", response_model=list[UsuarioDTO], tags=["Administración de usuarios"],
            summary="Control de proveedores")
def listar_proveedores(
    response: Response,
    validado: bool | None = Query(default=None),
    tipo_servicio: str | None = Query(default=None),
    limite: int = Query(default=20, ge=1, le=100),
    desplazamiento: int = Query(default=0, ge=0),
    _: UsuarioActual = SOLO_ADMIN,
    db: Session = Depends(get_db),
):
    proveedores, total = usuario_service.listar_proveedores(db, validado=validado, tipo_servicio=tipo_servicio,
                                                            limite=limite, desplazamiento=desplazamiento)
    response.headers["X-Total-Count"] = str(total)
    return proveedores


@router.patch("/proveedores/{usuario_id}", response_model=UsuarioDTO, tags=["Administración de usuarios"],
              summary="Validar a un proveedor")
def validar_proveedor(usuario_id: str, datos: ValidacionProveedorDTO, _: UsuarioActual = SOLO_ADMIN,
                      db: Session = Depends(get_db)):
    return usuario_service.validar_proveedor(db, usuario_id, datos.validado)
