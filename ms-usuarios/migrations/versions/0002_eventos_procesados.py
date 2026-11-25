"""eventos procesados

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('eventos_procesados',
    sa.Column('id_evento', sa.String(length=36), nullable=False),
    sa.Column('tipo', sa.String(length=100), nullable=False),
    sa.Column('procesado_en', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id_evento')
    )


def downgrade():
    op.drop_table('eventos_procesados')
