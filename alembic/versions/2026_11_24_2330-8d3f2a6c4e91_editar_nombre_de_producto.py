"""editar nombre de producto: nombre fijado e historial

Revision ID: 8d3f2a6c4e91
Revises: 5c1a9e7d2b40
Create Date: 2026-11-24 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d3f2a6c4e91'
down_revision: Union[str, Sequence[str], None] = '5c1a9e7d2b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Ningún nombre existente queda fijado: las cargas siguen actualizándolos como hasta ahora.
    op.add_column(
        'products',
        sa.Column('name_locked', sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_table(
        'product_name_changes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('old_name', sa.String(length=200), nullable=False),
        sa.Column('new_name', sa.String(length=200), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('changed_by', sa.String(length=80), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ['product_id'], ['products.id'],
            name=op.f('fk_product_name_changes_product_id_products'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_product_name_changes_user_id_users'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_product_name_changes')),
    )
    op.create_index(
        op.f('ix_product_name_changes_product_id'), 'product_name_changes', ['product_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_product_name_changes_product_id'), table_name='product_name_changes')
    op.drop_table('product_name_changes')
    op.drop_column('products', 'name_locked')
