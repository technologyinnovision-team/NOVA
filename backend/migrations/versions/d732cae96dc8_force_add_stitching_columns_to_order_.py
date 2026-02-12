"""force add stitching columns to order_items

Revision ID: d732cae96dc8
Revises: 64c268925bcb
Create Date: 2026-01-11 20:06:03.094685

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd732cae96dc8'
down_revision = '64c268925bcb'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('order_items')]

    if 'stitching_service_id' not in columns:
        op.add_column('order_items', sa.Column('stitching_service_id', sa.Integer(), nullable=True))
        op.create_foreign_key(None, 'order_items', 'stitching_services', ['stitching_service_id'], ['id'])
    
    if 'stitching_cost' not in columns:
        op.add_column('order_items', sa.Column('stitching_cost', sa.Numeric(10, 2), nullable=True))


def downgrade():
    op.drop_constraint(None, 'order_items', type_='foreignkey')
    op.drop_column('order_items', 'stitching_cost')
    op.drop_column('order_items', 'stitching_service_id')
