from sqlalchemy import create_engine, text
import os

pg_host = os.environ.get('PGHOST', 'localhost')
pg_port = os.environ.get('PGPORT', '5432')
pg_user = os.environ.get('PGUSER', 'postgres')
pg_db = os.environ.get('PGDATABASE', 'cognitiva_tcc')

dsn = f'postgresql://{pg_user}@{pg_host}:{pg_port}/{pg_db}'
print('DSN used:', dsn)
engine = create_engine(dsn)
with engine.connect() as conn:
    print('--- Tabelas públicas ---')
    tables = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"))
    for row in tables:
        print('-', row[0])

    print('\n--- Colunas: appointment ---')
    cols = conn.execute(text("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='appointment' ORDER BY ordinal_position"))
    for c in cols:
        print(c)

    print('\n--- Constraints: appointment ---')
    cons = conn.execute(text("SELECT constraint_name, constraint_type FROM information_schema.table_constraints WHERE table_name='appointment'"))
    for r in cons:
        print(r)

    print('\n--- Colunas: oauth_credential ---')
    cols2 = conn.execute(text("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='oauth_credential' ORDER BY ordinal_position"))
    for c in cols2:
        print(c)

    print('\n--- Constraints: oauth_credential ---')
    cons2 = conn.execute(text("SELECT constraint_name, constraint_type FROM information_schema.table_constraints WHERE table_name='oauth_credential'"))
    for r in cons2:
        print(r)

print('\nDone')
