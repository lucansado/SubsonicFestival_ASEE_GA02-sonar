# ms-usuarios · Usuarios, entradas y favoritos

Microservicio de la ASEE de Subsonic Festival (GA02). El contrato está en [openapi.yaml](openapi.yaml).

**Tecnologías:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, PostgreSQL 16, RabbitMQ (pika), httpx, Firebase Admin SDK, Docker.
**Puerto:** 8003 · **BD:** `usuarios_db` (PostgreSQL, puerto 5433 en tu equipo).
**Depende de:** ms-espacios (reserva de aforo, puerto 8002) y ms-escaleta (nombre de artistas, puerto 8001).

## Arrancar con Docker (recomendado)

```bash
# 1) Arrancar RabbitMQ desde una copia de la rama infra: cd infra && docker compose up -d
#    Crea la red externa subsonic, necesaria para este compose.
# 2) Para comprar entradas, arrancar también ms-espacios en su propia copia.
# 3) En la rama ms-usuarios:
cd ms-usuarios
docker compose up --build
docker compose exec ms-usuarios python scripts/poblar_bd.py    # datos de prueba
```

API y documentación: http://localhost:8003/docs

El poblado crea a David, Ana, Jose y Lucía y publica `usuarios.usuario.registrado`
por cada usuario nuevo. Añade a David tres favoritos (Martin Garrix, Armin van
Buuren y Skrillex), con los UUID del poblado de ms-escaleta, y publica
`usuarios.favorito.anadido` por cada favorito nuevo. En el entorno global, poblar
ms-escaleta antes de ms-usuarios para que analítica ya tenga sus géneros.

Se puede repetir: conserva los perfiles y favoritos existentes y solo publica
las nuevas inserciones, después del commit. Si los usuarios ya estaban creados
con el script antiguo, no se reenvía su registro automáticamente; para una demo
desde cero, ejecutar el poblado sobre bases de datos de prueba vacías. RabbitMQ
y el consumidor de analítica deben estar arrancados; sin `RABBITMQ_URL` los
eventos solo se escriben en el log.

Al arrancar se ejecuta `alembic upgrade head` antes de iniciar el consumidor de la cola `ms-usuarios`.
El contenedor usa `rabbitmq:5672`; para ejecutar Python en el equipo se usa `localhost:5672`.
El archivo `.env` también lo lee Compose: si has configurado allí la URL local, cámbiala al nombre
`rabbitmq` antes de levantar el contenedor. Sin credenciales, Firebase permanece simulado.

## Desarrollar en local (con recarga automática)

```bash
cd ms-usuarios
docker compose up -d usuarios-db      # solo la base de datos
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                # Mac/Linux: cp .env.example .env
python scripts/poblar_bd.py
python main.py
```

## Tests

```bash
pytest -q
```

Usan una base de datos SQLite temporal creada con las migraciones. Fuerzan Firebase y RabbitMQ
en modo local aunque exista un `.env`, así que no contactan con cuentas ni brokers reales.
Cubren los endpoints existentes, los 11 eventos, destinatarios y preferencias, mensajes repetidos,
rollback, reintentos/DLQ, el SDK de Firebase con dobles de prueba y las migraciones (incluido SQL
para PostgreSQL). La prueba contra Firebase real se ejecuta por separado, como se explica abajo.

## Autenticación

El API Gateway valida el JWT de Firebase y añade las cabeceras `X-User-Id`, `X-User-Rol` y `X-User-Email`.
Sin gateway, escríbelas tú en `/docs`. Ejemplos con los usuarios de prueba:

| Usuario | X-User-Id | X-User-Rol |
|---|---|---|
| Cliente | `uid-cliente-david` | `CLIENTE` |
| Proveedor | `uid-proveedor-ana` | `PROVEEDOR` |
| Administrador | `uid-admin-jose` | `ADMIN` |
| Staff de acceso | `uid-staff-lucia` | `STAFF` |

Para **registrar** un perfil nuevo basta con `X-User-Id` y `X-User-Email`: el usuario todavía no tiene rol.

## Dispositivos para notificaciones push

`POST /api/v1/usuarios/me/dispositivos` registra el token del dispositivo.
Al cerrar sesión, `DELETE /api/v1/usuarios/me/dispositivos/{fcm_token}` lo da de baja
solo para el usuario autenticado. Devuelve `204` sin cuerpo aunque el token no estuviera
registrado o no existieran preferencias. El token puede contener `:` y codificarse para URL.
Al eliminar el último token, los cambios de escaleta dejan de generar avisos `[push]` para
ese usuario hasta que registre otro dispositivo; sus preferencias de canales se conservan.

## Flujo de compra de una entrada

1. `POST /api/v1/usuarios/me/entradas` llama a ms-espacios (`/internal/v1/.../reservas-aforo`) con un timeout de 2 s y 3 reintentos.
2. Cobra en la **pasarela simulada**. Los tokens que empiezan por `tok_rechazado` devuelven 402 y liberan la reserva.
3. Guarda la entrada con un **QR firmado con HMAC** (`SUBSONIC|entrada|evento|firma`) y publica `usuarios.entrada.comprada`.

Si ms-espacios no responde, devuelve **503** con la cabecera `Retry-After: 5`.

## Migraciones (semana 2)

La revisión `0001` crea las cinco tablas de la semana 1, con sus claves, índices, UUID y JSONB
en PostgreSQL. `0002` añade `eventos_procesados` para detectar mensajes repetidos.
Tanto la API como `scripts/poblar_bd.py` ejecutan las migraciones antes de usar la BD.
La URL se obtiene de `config/settings.py`, también al usar la CLI de Alembic.

```bash
alembic upgrade head
alembic current
# Tras modificar los modelos:
alembic revision --autogenerate -m "descripcion del cambio"
# Revisar siempre la migración generada antes de aplicarla.
```

Si la BD todavía tiene las tablas de la semana 1 creadas con `create_all`, haz una copia de seguridad
y comprueba que su esquema coincide con esa versión. Después, con la API detenida:

```bash
alembic stamp 0001
alembic upgrade head
```

En Docker, con `usuarios-db` levantado y la imagen construida:

```bash
docker compose run --rm ms-usuarios alembic stamp 0001
docker compose run --rm ms-usuarios alembic upgrade head
```

No uses `stamp head` sobre la BD antigua: marcaría como aplicada la creación de
`eventos_procesados` sin crearla. Una BD vacía solo necesita `upgrade head`.

## Firebase Authentication real

Se necesita el JSON de la cuenta de servicio del monolito. Se comparte **fuera de Git**;
no se incluye en la imagen Docker. `.gitignore` y `.dockerignore` excluyen `.env`,
`firebase-claves.json` y `secrets/`.

Para Python local, copia `.env.example` a `.env` y configura una ruta absoluta:

```dotenv
FIREBASE_CREDENCIALES=C:/ruta/privada/firebase-claves.json
```

Para Docker se utiliza un archivo Compose adicional, que monta ese archivo en solo lectura
y rechaza una ruta inexistente:

```bash
docker compose -f docker-compose.yml -f docker-compose.firebase.yml up --build
```

El registro asigna el claim `rol` conservando otros claims existentes. Los cambios de rol
administrativos también se sincronizan. El cliente debe renovar su ID token para recibirlos.
El borrado elimina la cuenta en Firebase; si ya no existe, puede reintentarse sin error.
Un fallo de Firebase al registrar o borrar revierte los cambios SQL y permite reintentar.
No hay una transacción distribuida entre Firebase y PostgreSQL.

Una ruta de credenciales configurada pero inválida hace fallar el arranque; solo el valor vacío
activa la simulación. Referencia: [custom claims](https://firebase.google.com/docs/auth/admin/custom-claims)
y [gestión de usuarios](https://firebase.google.com/docs/auth/admin/manage-users).

Con la API usando esas mismas credenciales, ejecutar desde el equipo:

```bash
python scripts/comprobar_firebase.py --api-url http://localhost:8003
```

El script crea una cuenta temporal propia, registra el perfil mediante HTTP, consulta el claim
en Firebase y comprueba que el borrado de la API la elimina allí. Solo limpia la cuenta que él
mismo ha creado. No envía correos ni requiere un usuario personal.
Esta comprobación necesita las credenciales reales; los tests normales no la sustituyen.

## Eventos y notificaciones

`eventos/publicador.py` y `eventos/consumidor.py` parten de la plantilla de `infra`
(commit `7fa06bc`). Son copias dentro del servicio, sin importar código de otras ramas.
El consumidor añade validación de mensajes y confirmación del broker antes de dar por
reenviado un reintento. Arranca en un hilo en el `lifespan` y se detiene al cerrar la API.

| Evento consumido | Resultado |
|---|---|
| `escaleta.pase.modificado` / `cancelado` | Push a la intersección de favoritos y compradores con entrada activa; texto específico para cancelaciones |
| `espacios.evento.cancelado` | Cancela y reembolsa entradas activas o con cancelación solicitada, publica sus cancelaciones y avisa a compradores |
| `escaleta.artista.actualizado` | Renombra el artista en los favoritos |
| `escaleta.publicada` | Push a compradores con entrada activa, una vez por usuario |
| `espacios.alquiler.solicitado` | Aviso a administradores activos |
| `espacios.alquiler.aprobado` / `rechazado` | Push y email al proveedor |
| `tienda.pedido.creado` / `actualizado` | Email de confirmación y cambios de estado, incluido envío y punto de recogida |
| `tienda.stock.bajo` | Aviso a administradores activos |

Se respetan las preferencias de cada usuario, los tokens disponibles y los canales de cada
aviso. Las cuentas inactivas o eliminadas no reciben notificaciones. Push y email siguen
siendo **simulados mediante log**; el envío FCM era opcional en el reparto. La pasarela de
cobro y reembolso también sigue simulada.

Sin `RABBITMQ_URL`, el publicador escribe en el log y el consumidor no arranca. Con RabbitMQ,
se usa `subsonic.events`, la cola duradera `ms-usuarios` y las 11 claves de la tabla. El broker
de `infra` debe tener declarados `subsonic.dlx` y `subsonic.dlq`.

Cada mensaje abre una sesión SQL. Su `id_evento` y sus cambios en BD se guardan en la misma
transacción; una entrega repetida ya completada se ignora. Si falla, se revierte la transacción,
se reintenta tres veces y después se envía a la DLQ. Un reintento no confirmado por el broker
no recibe `ack`. El `correlation_id` se conserva en los eventos publicados desde el manejador.

La plantilla de publicación conserva su comportamiento: si falla dos veces, deja
`EVENTO NO PUBLICADO` en el log para reenviarlo. No hay outbox transaccional. El registro de
recepciones evita repetir mensajes completados, pero no garantiza una única ejecución de
efectos externos ante una caída entre el envío/reembolso y el commit SQL.
