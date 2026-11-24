"""editar código de barras: permiso por usuario e historial

Revision ID: 5c1a9e7d2b40
Revises: 1e2d01aa2464
Create Date: 2026-11-24 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c1a9e7d2b40'
down_revision: Union[str, Sequence[str], None] = '1e2d01aa2464'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Los usuarios existentes quedan sin el permiso; los administradores no lo necesitan.
    op.add_column(
        'users',
        sa.Column('can_edit_barcodes', sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_table(
        'barcode_changes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('old_ean', sa.String(length=14), nullable=True),
        sa.Column('new_ean', sa.String(length=14), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('changed_by', sa.String(length=80), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ['product_id'], ['products.id'],
            name=op.f('fk_barcode_changes_product_id_products'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_barcode_changes_user_id_users'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_barcode_changes')),
    )
    op.create_index(
        op.f('ix_barcode_changes_product_id'), 'barcode_changes', ['product_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_barcode_changes_product_id'), table_name='barcode_changes')
    op.drop_table('barcode_changes')
    op.drop_column('users', 'can_edit_barcodes')
