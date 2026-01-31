"""Runner simples de migrations SQL.

Uso:
  - Configure `DATABASE_URL` no ambiente (ex.: export DATABASE_URL=postgresql://user:pass@host:5432/dbname)
  - Execute: python run_migrations.py

O script criará uma tabela `migrations_applied` para controlar migrações aplicadas e executará os arquivos
SQL presentes em `calendar-api/migrations/` na ordem lexicográfica.

Atenção: Backup do banco é recomendado antes de executar.
"""
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

MIGRATIONS_DIR = os.path.dirname(__file__)


def get_database_url():
    url = os.environ.get('DATABASE_URL')
    if url:
        return url

    # Fallback: montar a URL a partir das variáveis PG* (útil quando a variável DATABASE_URL
    # causa problemas de parsing em alguns ambientes Windows/PowerShell).
    pg_host = os.environ.get('PGHOST', 'localhost')
    pg_port = os.environ.get('PGPORT', '5432')
    pg_user = os.environ.get('PGUSER', 'postgres')
    pg_password = os.environ.get('PGPASSWORD')
    pg_db = os.environ.get('PGDATABASE', 'cognitiva_tcc')

    if not pg_password:
        print('ERRO: nem DATABASE_URL nem PGPASSWORD definidos. Defina DATABASE_URL ou exporte PGPASSWORD/PGHOST/PGUSER/PGDATABASE/PGPORT.')
        sys.exit(1)

    # Construir URL de forma segura
    try:
        from sqlalchemy.engine import URL
        url_obj = URL.create(
            drivername='postgresql+psycopg2',
            username=pg_user,
            password=pg_password,
            host=pg_host,
            port=int(pg_port),
            database=pg_db
        )
        return str(url_obj)
    except Exception as e:
        print(f'ERRO ao montar DATABASE_URL a partir de variáveis PG*: {e}')
        sys.exit(1)


def ensure_migrations_table(engine):
    with engine.connect() as conn:
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS migrations_applied (
                id SERIAL PRIMARY KEY,
                filename TEXT UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT now()
            )
        '''))
        conn.commit()


def get_applied_migrations(engine):
    with engine.connect() as conn:
        result = conn.execute(text('SELECT filename FROM migrations_applied'))
        applied = {row[0] for row in result.fetchall()}
    return applied


def apply_migration_file(engine, path, filename):
    with open(path, 'r', encoding='utf-8') as f:
        sql = f.read()
    print(f'Aplicando {filename}...')
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
            conn.execute(text("INSERT INTO migrations_applied (filename) VALUES (:fn)"), {'fn': filename})
        print(f'Aplicado {filename}')
    except SQLAlchemyError as e:
        print(f'Erro ao aplicar {filename}: {e}')
        raise


def main():
    db_url = get_database_url()
    engine = create_engine(db_url)

    ensure_migrations_table(engine)
    applied = get_applied_migrations(engine)

    files = sorted([f for f in os.listdir(MIGRATIONS_DIR) if f.endswith('.sql')])
    pending = [f for f in files if f not in applied]

    if not pending:
        print('Nenhuma migration pendente.')
        return

    for filename in pending:
        path = os.path.join(MIGRATIONS_DIR, filename)
        apply_migration_file(engine, path, filename)

    print('Todas as migrations pendentes foram aplicadas.')


if __name__ == '__main__':
    main()
