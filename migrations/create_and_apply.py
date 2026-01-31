import traceback
from sqlalchemy import create_engine, text
import os

# Constrói engine usando variáveis PG* para evitar parsing problemático de DATABASE_URL
pg_host = os.environ.get('PGHOST', 'localhost')
pg_port = os.environ.get('PGPORT', '5432')
pg_user = os.environ.get('PGUSER', 'postgres')
pg_db = os.environ.get('PGDATABASE', 'cognitiva_tcc')

# DSN sem password (usamos PGPASSWORD no ambiente para autenticação)
dsn = f'postgresql://{pg_user}@{pg_host}:{pg_port}/{pg_db}'
print('DSN (used):', dsn)
engine = create_engine(dsn)

create_sql = '''
CREATE TABLE IF NOT EXISTS appointment (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    appointment_date TIMESTAMP WITH TIME ZONE NOT NULL,
    service_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'agendado',
    google_event_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT now()
);
'''

MIGRATIONS_DIR = os.path.dirname(__file__)

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

def get_applied(engine):
    with engine.connect() as conn:
        result = conn.execute(text('SELECT filename FROM migrations_applied'))
        return {row[0] for row in result.fetchall()}

def apply_file(engine, path, filename):
    with open(path, 'r', encoding='utf-8') as f:
        sql = f.read()
    print(f'Aplicando {filename}...')
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
            conn.execute(text("INSERT INTO migrations_applied (filename) VALUES (:fn)"), {'fn': filename})
        print(f'Aplicado {filename}')
    except Exception as e:
        print(f'Erro ao aplicar {filename}: {e}')
        raise

try:
    # Criar tabela appointment caso não exista
    with engine.begin() as conn:
        conn.execute(text(create_sql))
    print('Tabela appointment criada (ou já existia).')

    # Preparar e aplicar migrations SQL da pasta
    ensure_migrations_table(engine)
    applied = get_applied(engine)
    files = sorted([f for f in os.listdir(MIGRATIONS_DIR) if f.endswith('.sql')])
    pending = [f for f in files if f not in applied]
    if not pending:
        print('Nenhuma migration pendente.')
    for filename in pending:
        path = os.path.join(MIGRATIONS_DIR, filename)
        apply_file(engine, path, filename)
    print('Todas as migrations pendentes foram aplicadas.')
except Exception:
    traceback.print_exc()
    raise
