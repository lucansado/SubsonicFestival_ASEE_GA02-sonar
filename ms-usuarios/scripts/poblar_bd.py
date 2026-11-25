# ms-usuarios/scripts/poblar_bd.py
# Datos de prueba iniciales (los usuarios de la versión monolítica más un usuario de staff).
# Los UID son ficticios: en producción son los UID de Firebase. Coinciden con los de los demás servicios.
# Uso: python scripts/poblar_bd.py   (desde la carpeta ms-usuarios)
import sys
from pathlib import Path
from uuid import UUID

sys.path.append(str(Path(__file__).resolve().parent.parent))

from config.database import SessionLocal, crear_tablas  # noqa: E402
from eventos.publicador import publicar  # noqa: E402
from model.models import ArtistaFavorito, Proveedor, Usuario  # noqa: E402

# UUID y nombres del poblado de ms-escaleta; no requiere llamadas HTTP entre servicios.
FAVORITOS_DAVID = [
    (UUID("22222222-2222-4222-8222-000000000001"), "Martin Garrix"),
    (UUID("22222222-2222-4222-8222-000000000004"), "Armin van Buuren"),
    (UUID("22222222-2222-4222-8222-000000000009"), "Skrillex"),
]


def usuarios_de_prueba() -> list[Usuario]:
    return [
        Usuario(id="uid-cliente-david", email="cliente@subsonic.com", nombre="David", apellidos="García López",
                direccion="Calle Mayor 10, Cáceres", telefono="+34 600 111 222", rol="CLIENTE"),
        Usuario(id="uid-proveedor-ana", email="proveedor@subsonic.com", nombre="Ana", apellidos="Martínez Ruiz",
                direccion="Avenida de la Paz 5, Madrid", telefono="+34 600 333 444", rol="PROVEEDOR",
                proveedor=Proveedor(nombre_comercial="Ana Food Truck", cif="B12345678", tipo_servicio="food-truck",
                                    descripcion_servicio="Puesto de comida y bebida artesanal para festivales.",
                                    validado=True)),
        Usuario(id="uid-admin-jose", email="admin@subsonic.com", nombre="Jose", apellidos="Nogales Sánchez",
                direccion="Plaza de España 1, Sevilla", telefono="+34 600 555 666", rol="ADMIN"),
        Usuario(id="uid-staff-lucia", email="staff@subsonic.com", nombre="Lucía", apellidos="Pérez Gil", rol="STAFF"),
    ]


def poblar() -> None:
    crear_tablas()
    with SessionLocal() as db:
        nuevos = []
        for usuario in usuarios_de_prueba():
            if not db.get(Usuario, usuario.id):
                db.add(usuario)
                nuevos.append(usuario)
        db.commit()
        # Igual que en el registro por la API: publicar solo después de guardar.
        for usuario in nuevos:
            publicar("usuarios.usuario.registrado", {"usuario_id": usuario.id, "rol": usuario.rol})

        favoritos_nuevos = []
        david = db.get(Usuario, "uid-cliente-david")
        if david.activo and not david.eliminado_en:
            for artista_id, nombre in FAVORITOS_DAVID:
                if not db.get(ArtistaFavorito, (david.id, artista_id)):
                    favorito = ArtistaFavorito(usuario_id=david.id, artista_id=artista_id, artista_nombre=nombre)
                    db.add(favorito)
                    favoritos_nuevos.append(favorito)
        db.commit()
        for favorito in favoritos_nuevos:
            publicar("usuarios.favorito.anadido", {
                "usuario_id": favorito.usuario_id, "artista_id": str(favorito.artista_id),
                "artista_nombre": favorito.artista_nombre,
            })
        print(f"[OK] {len(nuevos)} usuarios y {len(favoritos_nuevos)} favoritos nuevos; eventos publicados")


if __name__ == "__main__":
    poblar()
