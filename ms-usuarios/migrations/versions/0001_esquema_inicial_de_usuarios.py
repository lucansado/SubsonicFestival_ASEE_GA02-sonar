"""esquema inicial de usuarios

Revision ID: 0001
Revises: None
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('usuarios',
    sa.Column('id', sa.String(length=128), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=True),
    sa.Column('apellidos', sa.String(length=255), nullable=True),
    sa.Column('telefono', sa.String(length=20), nullable=True),
    sa.Column('direccion', sa.String(length=255), nullable=True),
    sa.Column('rol', sa.String(length=20), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('eliminado_en', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('artistas_favoritos',
    sa.Column('usuario_id', sa.String(length=128), nullable=False),
    sa.Column('artista_id', sa.Uuid(), nullable=False),
    sa.Column('artista_nombre', sa.String(length=255), nullable=True),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('usuario_id', 'artista_id')
    )
    op.create_table('entradas',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('usuario_id', sa.String(length=128), nullable=False),
    sa.Column('evento_id', sa.String(length=100), nullable=False),
    sa.Column('evento_titulo', sa.String(length=200), nullable=True),
    sa.Column('evento_fechas', sa.String(length=100), nullable=True),
    sa.Column('evento_fecha_inicio', sa.Date(), nullable=True),
    sa.Column('evento_fecha_fin', sa.Date(), nullable=True),
    sa.Column('tipo_pase', sa.String(length=20), nullable=False),
    sa.Column('precio_pagado', sa.Numeric(precision=8, scale=2), nullable=False),
    sa.Column('estado', sa.String(length=30), nullable=False),
    sa.Column('codigo_qr', sa.String(length=255), nullable=False),
    sa.Column('reserva_id', sa.Uuid(), nullable=True),
    sa.Column('pago_ref', sa.String(length=100), nullable=True),
    sa.Column('motivo_cancelacion', sa.Text(), nullable=True),
    sa.Column('comprada_en', sa.DateTime(timezone=True), nullable=False),
    sa.Column('usada_en', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_entradas_evento_id'), 'entradas', ['evento_id'], unique=False)
    op.create_index(op.f('ix_entradas_usuario_id'), 'entradas', ['usuario_id'], unique=False)
    op.create_table('preferencias_notificacion',
    sa.Column('usuario_id', sa.String(length=128), nullable=False),
    sa.Column('push', sa.Boolean(), nullable=False),
    sa.Column('email', sa.Boolean(), nullable=False),
    sa.Column('fcm_tokens', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('usuario_id')
    )
    op.create_table('proveedores',
    sa.Column('usuario_id', sa.String(length=128), nullable=False),
    sa.Column('nombre_comercial', sa.String(length=200), nullable=True),
    sa.Column('cif', sa.String(length=20), nullable=True),
    sa.Column('tipo_servicio', sa.String(length=100), nullable=True),
    sa.Column('descripcion_servicio', sa.Text(), nullable=True),
    sa.Column('validado', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('usuario_id')
    )


def downgrade():
    op.drop_table('proveedores')
    op.drop_table('preferencias_notificacion')
    op.drop_index(op.f('ix_entradas_usuario_id'), table_name='entradas')
    op.drop_index(op.f('ix_entradas_evento_id'), table_name='entradas')
    op.drop_table('entradas')
    op.drop_table('artistas_favoritos')
    op.drop_table('usuarios')
