# ms-usuarios/controller/entradas_controller.py
# Endpoints de entradas (compra, cancelación, validación) y favoritos
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session
from config.database import get_db
from config.seguridad import UsuarioActual, requiere_rol
from model.dto.entrada_dto import (
    CompraEntradaDTO, EntradaDTO, EstadoEntrada, FavoritoDTO, FavoritoEntradaDTO, ResolucionCancelacionDTO,
    SolicitudCancelacionDTO, ValidacionDTO, ValidacionEntradaDTO,
)
from service import entrada_service

router = APIRouter()
SOLO_CLIENTE = Depends(requiere_rol("cliente"))
SOLO_ADMIN = Depends(requiere_rol("admin"))


# ── Entradas del cliente ────────────────────────────────────

@router.get("/usuarios/me/entradas", response_model=list[EntradaDTO], tags=["Entradas"],
            summary="Entradas del cliente")
def listar_mis_entradas(estado: EstadoEntrada | None = Query(default=None), usuario: UsuarioActual = SOLO_CLIENTE,
                        db: Session = Depends(get_db)):
    return entrada_service.mis_entradas(db, usuario.id, estado)


@router.post("/usuarios/me/entradas", response_model=EntradaDTO, status_code=status.HTTP_201_CREATED,
             tags=["Entradas"], summary="Comprar una entrada")
def comprar_entrada(datos: CompraEntradaDTO, response: Response, usuario: UsuarioActual = SOLO_CLIENTE,
                    db: Session = Depends(get_db)):
    entrada = entrada_service.comprar(db, usuario.id, datos)
    response.headers["Location"] = f"/api/v1/usuarios/me/entradas/{entrada.id}"
    return entrada


@router.get("/usuarios/me/entradas/{entrada_id}", response_model=EntradaDTO, tags=["Entradas"],
            summary="Obtener una entrada propia")
def obtener_mi_entrada(entrada_id: str, usuario: UsuarioActual = SOLO_CLIENTE, db: Session = Depends(get_db)):
    return entrada_service.mi_entrada(db, usuario.id, entrada_id)


@router.post("/usuarios/me/entradas/{entrada_id}/cancelaciones", response_model=EntradaDTO,
             status_code=status.HTTP_201_CREATED, tags=["Entradas"],
             summary="Solicitar la cancelación de una entrada")
def solicitar_cancelacion(entrada_id: str, datos: SolicitudCancelacionDTO, usuario: UsuarioActual = SOLO_CLIENTE,
                          db: Session = Depends(get_db)):
    return entrada_service.solicitar_cancelacion(db, usuario.id, entrada_id, datos.motivo)


# ── Administración y control de acceso ──────────────────────

@router.get("/entradas", response_model=list[EntradaDTO], tags=["Entradas"],
            summary="Listar entradas (administración)")
def listar_entradas(
    response: Response,
    evento_id: str | None = Query(default=None),
    estado: EstadoEntrada | None = Query(default=None),
    limite: int = Query(default=20, ge=1, le=100),
    desplazamiento: int = Query(default=0, ge=0),
    _: UsuarioActual = SOLO_ADMIN,
    db: Session = Depends(get_db),
):
    entradas, total = entrada_service.listar_entradas(db, evento_id=evento_id, estado=estado.value if estado else None,
                                                      limite=limite, desplazamiento=desplazamiento)
    response.headers["X-Total-Count"] = str(total)
    return entradas


@router.post("/entradas/validaciones", response_model=ValidacionDTO, status_code=status.HTTP_201_CREATED,
             tags=["Entradas"], summary="Validar una entrada en el control de acceso")
def validar_entrada(datos: ValidacionEntradaDTO, _: UsuarioActual = Depends(requiere_rol("staff", "admin")),
                    db: Session = Depends(get_db)):
    return entrada_service.validar(db, datos.codigo_qr, datos.evento_id)


@router.patch("/entradas/{entrada_id}", response_model=EntradaDTO, tags=["Entradas"],
              summary="Resolver una solicitud de cancelación")
def resolver_cancelacion(entrada_id: str, datos: ResolucionCancelacionDTO, _: UsuarioActual = SOLO_ADMIN,
                         db: Session = Depends(get_db)):
    return entrada_service.resolver_cancelacion(db, entrada_id, datos.estado)


# ── Favoritos ───────────────────────────────────────────────

@router.get("/usuarios/me/favoritos", response_model=list[FavoritoDTO], tags=["Favoritos"],
            summary="Artistas favoritos del cliente")
def listar_favoritos(usuario: UsuarioActual = SOLO_CLIENTE, db: Session = Depends(get_db)):
    return entrada_service.listar_favoritos(db, usuario.id)


@router.post("/usuarios/me/favoritos", response_model=FavoritoDTO, status_code=status.HTTP_201_CREATED,
             tags=["Favoritos"], summary="Añadir un artista a favoritos")
def anadir_favorito(datos: FavoritoEntradaDTO, usuario: UsuarioActual = SOLO_CLIENTE, db: Session = Depends(get_db)):
    return entrada_service.anadir_favorito(db, usuario.id, datos.artista_id)


@router.delete("/usuarios/me/favoritos/{artista_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Favoritos"],
               summary="Quitar un artista de favoritos")
def quitar_favorito(artista_id: UUID, usuario: UsuarioActual = SOLO_CLIENTE, db: Session = Depends(get_db)):
    entrada_service.quitar_favorito(db, usuario.id, artista_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
