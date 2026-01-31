"""Migração segura: encripta tokens legados em `oauth_credential.token` usando AES-GCM.

Como funciona:
- Verifica se `TOKEN_ENCRYPTION_KEY` está definida (base64 urlsafe, 16/24/32 bytes).
- Faz backup (arquivo JSON local) com os registros que serão migrados (APENAS local, tokens sensíveis).
- Para cada registro com `token IS NOT NULL` e `token_encrypted IS NULL`, aplica `encrypt_token` do helper `src.lib.crypto` e atualiza os campos `token_encrypted`, `token_nonce`, limpando `token`.
- Opera dentro de uma transação para cada registro; registra resumo no final.

Uso (PowerShell):
  $env:TOKEN_ENCRYPTION_KEY = '<base64_urlsafe_32bytes>'
  $env:DATABASE_URL = 'postgresql://user:pass@host:5432/db'
  py -3 migrations\migrate_tokens_to_encrypted.py

IMPORTANTE:
- Faça backup do banco antes de rodar em produção.
- Após migração, rotacione chaves e trate tokens com cuidado.
"""
import os
import sys
import json
import datetime
import base64
from sqlalchemy import create_engine, text

# Garantir import do pacote `src`
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from src.lib import crypto
except Exception as e:
    print('Erro ao importar helper de crypto:', e)
    raise


def get_database_url():
    return os.environ.get('DATABASE_URL') or f"sqlite:///{os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'database', 'app.db'))}"


def backup_records(records):
    now = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    filename = os.path.join(os.path.dirname(__file__), f'oauth_credential_backup_{now}.json')
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    return filename


def main():
    key = os.environ.get('TOKEN_ENCRYPTION_KEY')
    if not key:
        print('TOKEN_ENCRYPTION_KEY não está definida. Abortando.')
        raise SystemExit(2)

    db_url = get_database_url()
    print('Usando DB:', db_url)
    engine = create_engine(db_url)

    with engine.connect() as conn:
        # selecionar registros que precisam de migração
        rows = conn.execute(text("SELECT id, token FROM oauth_credential WHERE token IS NOT NULL AND (token_encrypted IS NULL OR token_encrypted='')")).fetchall()
        if not rows:
            print('Nenhum token legado encontrado para migrar.')
            return

        # Criar backup (ID + token) localmente
        backup_data = [{'id': r['id'], 'token': r['token']} for r in rows]
        backup_file = backup_records(backup_data)
        print(f'Backup criado: {backup_file} ({len(rows)} registros)')

        migrated = 0
        for r in rows:
            rec_id = r['id']
            token = r['token']
            try:
                nonce, ciphertext = crypto.encrypt_token(token)
            except Exception as e:
                print(f'Falha ao encriptar token id={rec_id}:', e)
                continue

            # atualizar registro dentro de transação
            try:
                with conn.begin():
                    conn.execute(text(
                        "UPDATE oauth_credential SET token_encrypted = :ct, token_nonce = :nonce, token = NULL WHERE id = :id"
                    ), {'ct': ciphertext, 'nonce': nonce, 'id': rec_id})
                migrated += 1
            except Exception as e:
                print(f'Falha ao atualizar id={rec_id}:', e)
                continue

        print(f'Migração finalizada. Registros migrados: {migrated}/{len(rows)}')


if __name__ == '__main__':
    main()
