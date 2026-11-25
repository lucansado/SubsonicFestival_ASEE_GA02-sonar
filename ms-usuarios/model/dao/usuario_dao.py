# ms-usuarios/model/dao/usuario_dao.py
# Acceso a las tablas usuarios, proveedores y preferencias_notificacion
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload
from model.models import ArtistaFavorito, PreferenciasNotificacion, Proveedor, Usuario


class UsuarioDAO:
    def administradores_activos(self, db: Session) -> set[str]:
        return set(db.scalars(select(Usuario.id).where(
            Usuario.rol == "ADMIN", Usuario.activo.is_(True), Usuario.eliminado_en.is_(None)
        )).all())

    def obtener(self, db: Session, usuario_id: str, *, bloquear: bool = False) -> Usuario | None:
        consulta = select(Usuario).where(Usuario.id == usuario_id, Usuario.eliminado_en.is_(None)) \
            .options(selectinload(Usuario.proveedor))
        if bloquear:
            consulta = consulta.with_for_update(of=Usuario)
        return db.scalar(consulta)

    def existe(self, db: Session, usuario_id: str) -> bool:
        """Incluye las cuentas eliminadas (su UID no se puede volver a registrar)."""
        return db.get(Usuario, usuario_id) is not None

    def existe_email(self, db: Session, email: str) -> bool:
        return db.scalar(select(func.count()).select_from(Usuario).where(Usuario.email == email)) > 0

    def crear(self, db: Session, usuario: Usuario) -> Usuario:
        db.add(usuario)
        db.flush()
        return usuario

    def listar(self, db: Session, *, rol: str | None, activo: bool | None, q: str | None,
               limite: int, desplazamiento: int) -> tuple[list[Usuario], int]:
        consulta = select(Usuario).where(Usuario.eliminado_en.is_(None))
        if rol:
            consulta = consulta.where(Usuario.rol == rol)
        if activo is not None:
            consulta = consulta.where(Usuario.activo.is_(activo))
        if q:
            patron = f"%{q.lower()}%"
            consulta = consulta.where(or_(
                func.lower(Usuario.nombre).like(patron),
                func.lower(Usuario.apellidos).like(patron),
                func.lower(Usuario.email).like(patron),
            ))
        total = db.scalar(select(func.count()).select_from(consulta.subquery()))
        usuarios = db.scalars(
            consulta.options(selectinload(Usuario.proveedor))
            .order_by(Usuario.creado_en.desc()).limit(limite).offset(desplazamiento)
        ).all()
        return list(usuarios), total

    def listar_proveedores(self, db: Session, *, validado: bool | None, tipo_servicio: str | None,
                           limite: int, desplazamiento: int) -> tuple[list[Usuario], int]:
        consulta = select(Usuario).join(Proveedor).where(Usuario.eliminado_en.is_(None))
        if validado is not None:
            consulta = consulta.where(Proveedor.validado.is_(validado))
        if tipo_servicio:
            consulta = consulta.where(func.lower(Proveedor.tipo_servicio) == tipo_servicio.lower())
        total = db.scalar(select(func.count()).select_from(consulta.subquery()))
        usuarios = db.scalars(
            consulta.options(selectinload(Usuario.proveedor))
            .order_by(Usuario.creado_en.desc()).limit(limite).offset(desplazamiento)
        ).all()
        return list(usuarios), total

    def borrar_datos_relacionados(self, db: Session, usuario_id: str) -> None:
        """RGPD: favoritos, preferencias y datos de proveedor del usuario eliminado."""
        db.execute(delete(ArtistaFavorito).where(ArtistaFavorito.usuario_id == usuario_id))
        db.execute(delete(PreferenciasNotificacion).where(PreferenciasNotificacion.usuario_id == usuario_id))
        db.execute(delete(Proveedor).where(Proveedor.usuario_id == usuario_id))

    # ── Preferencias de notificación ─────────────────────────

    def obtener_preferencias(self, db: Session, usuario_id: str) -> PreferenciasNotificacion | None:
        return db.get(PreferenciasNotificacion, usuario_id)

    def obtener_o_crear_preferencias(self, db: Session, usuario_id: str) -> PreferenciasNotificacion:
        preferencias = db.get(PreferenciasNotificacion, usuario_id)
        if not preferencias:
            preferencias = PreferenciasNotificacion(usuario_id=usuario_id, push=True, email=True, fcm_tokens=[])
            db.add(preferencias)
            db.flush()
        return preferencias
