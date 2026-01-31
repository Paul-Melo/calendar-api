import os, traceback
from sqlalchemy import create_engine

print('DATABASE_URL (repr):', repr(os.environ.get('DATABASE_URL')))
try:
    engine = create_engine(os.environ['DATABASE_URL'])
    with engine.connect() as conn:
        print('Connected OK via SQLAlchemy')
except Exception as e:
    traceback.print_exc()
    print('EXCEPTION REPR:', repr(e))
