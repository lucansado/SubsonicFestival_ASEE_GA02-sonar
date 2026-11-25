# ms-usuarios/model/dao/entrada_dao.py
# Acceso a las tablas entradas y artistas_favoritos
from datetime import date
from uuid import UUID
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload
from model.models import ArtistaFavorito, Entrada


class EntradaDAO:
    def listar_de_usuario(self, db: Session, usuario_id: str, estado: str | None) -> list[Entrada]:
        consulta = select(Entrada).where(Entrada.usuario_id == usuario_id)
        if estado:
            consulta = consulta.where(Entrada.estado == estado)
        return list(db.scalars(consulta.order_by(Entrada.comprada_en.desc())).all())

    def listar(self, db: Session, *, evento_id: str | None, estado: str | None,
               limite: int, desplazamiento: int) -> tuple[list[Entrada], int]:
        consulta = select(Entrada)
        if evento_id:
            consulta = consulta.where(Entrada.evento_id == evento_id)
        if estado:
            consulta = consulta.where(Entrada.estado == estado)
        total = db.scalar(select(func.count()).select_from(consulta.subquery()))
        entradas = db.scalars(
            consulta.order_by(Entrada.comprada_en.desc()).limit(limite).offset(desplazamiento)
        ).all()
        return list(entradas), total

    def obtener(self, db: Session, entrada_id: str, *, bloquear: bool = False) -> Entrada | None:
        consulta = select(Entrada).where(Entrada.id == entrada_id).options(selectinload(Entrada.usuario))
        if bloquear:
            consulta = consulta.with_for_update(of=Entrada)
        return db.scalar(consulta)

    def crear(self, db: Session, entrada: Entrada) -> Entrada:
        db.add(entrada)
        db.flush()
        return entrada

    def tiene_entradas_pendientes(self, db: Session, usuario_id: str, hoy: date) -> bool:
        """Entradas activas (o con cancelación pendiente) de eventos que aún no han terminado."""
        return db.scalar(
            select(func.count()).select_from(Entrada).where(
                Entrada.usuario_id == usuario_id,
                Entrada.estado.in_(("ACTIVA", "CANCELACION_SOLICITADA")),
                Entrada.evento_fecha_fin >= hoy,
            )
        ) > 0

    def entradas_activas_de_evento(self, db: Session, evento_id: str) -> list[Entrada]:
        return list(db.scalars(
            select(Entrada).where(Entrada.evento_id == evento_id,
                                  Entrada.estado.in_(("ACTIVA", "CANCELACION_SOLICITADA")))
            .with_for_update()
        ).all())

    def usuarios_con_entrada(self, db: Session, evento_id: str) -> set[str]:
        return set(db.scalars(
            select(Entrada.usuario_id).where(Entrada.evento_id == evento_id, Entrada.estado == "ACTIVA")
        ).all())

    # ── Favoritos ────────────────────────────────────────────

    def listar_favoritos(self, db: Session, usuario_id: str) -> list[ArtistaFavorito]:
        return list(db.scalars(
            select(ArtistaFavorito).where(ArtistaFavorito.usuario_id == usuario_id)
            .order_by(ArtistaFavorito.creado_en.desc())
        ).all())

    def obtener_favorito(self, db: Session, usuario_id: str, artista_id: UUID) -> ArtistaFavorito | None:
        return db.get(ArtistaFavorito, (usuario_id, artista_id))

    def crear_favorito(self, db: Session, favorito: ArtistaFavorito) -> ArtistaFavorito:
        db.add(favorito)
        db.flush()
        return favorito

    def renombrar_artista(self, db: Session, artista_id: UUID, nombre: str) -> int:
        resultado = db.execute(
            update(ArtistaFavorito).where(ArtistaFavorito.artista_id == artista_id).values(artista_nombre=nombre)
        )
        return resultado.rowcount

    def usuarios_con_favorito(self, db: Session, artista_id: UUID) -> set[str]:
        return set(db.scalars(select(ArtistaFavorito.usuario_id).where(ArtistaFavorito.artista_id == artista_id)).all())
