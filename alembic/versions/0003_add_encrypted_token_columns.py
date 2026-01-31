"""Add encrypted token columns to oauth_credential

Revision ID: 0003_add_encrypted_token_columns
Revises: 0002_create_oauthcredential
Create Date: 2025-11-24
"""
from alembic import op
import sqlalchemy as sa
import os
import base64

# revision identifiers, used by Alembic.
revision = '0003_add_encrypted_token_columns'
down_revision = '0002_create_oauthcredential'
branch_labels = None
depends_on = None


def upgrade():
    # adicionar colunas para armazenamento encriptado
    op.add_column('oauth_credential', sa.Column('token_encrypted', sa.LargeBinary(), nullable=True))
    op.add_column('oauth_credential', sa.Column('token_nonce', sa.LargeBinary(), nullable=True))

    # Se houver chave presente em runtime, tente migrar tokens legados
    key = os.environ.get('TOKEN_ENCRYPTION_KEY')
    if key:
        try:
            from sqlalchemy import select
            conn = op.get_bind()
            rows = conn.execute(select(sa.text('id, token')).select_from(sa.text('oauth_credential'))).fetchall()
            # Import local helper to avoid heavy deps; perform simple AESGCM via cryptography
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            k = base64.urlsafe_b64decode(key)
            aes = AESGCM(k)
            for r in rows:
                if not r['token']:
                    continue
                nonce = os.urandom(12)
                ct = aes.encrypt(nonce, r['token'].encode('utf-8'), None)
                conn.execute(sa.text('UPDATE oauth_credential SET token_encrypted=:ct, token_nonce=:nonce, token=NULL WHERE id=:id'), {'ct': ct, 'nonce': nonce, 'id': r['id']})
        except Exception:
            # Se a migração automática falhar, não abortar; administrador pode migrar manualmente
            pass


def downgrade():
    op.drop_column('oauth_credential', 'token_nonce')
    op.drop_column('oauth_credential', 'token_encrypted')
