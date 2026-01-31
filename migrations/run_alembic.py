"""Utility to run alembic programmatically.

Usage (PowerShell):
  $env:DATABASE_URL = "postgresql://user:pass@localhost:5432/dbname"
  py -3 migrations\run_alembic.py upgrade head

This script requires `alembic` to be installed in the environment.
"""
import sys
import os
from alembic.config import Config
from alembic import command

HERE = os.path.dirname(__file__)
ALEMBIC_INI = os.path.join(HERE, '..', 'alembic.ini')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: run_alembic.py <command> [<rev>]. Example: run_alembic.py upgrade head')
        raise SystemExit(2)

    cmd = sys.argv[1]
    rev = sys.argv[2] if len(sys.argv) > 2 else None

    cfg = Config(ALEMBIC_INI)
    # supply database url from env if present
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        cfg.set_main_option('sqlalchemy.url', database_url)
    else:
        print('Warning: DATABASE_URL not set; alembic will use the value in alembic.ini')

    if cmd == 'upgrade':
        command.upgrade(cfg, rev or 'head')
    elif cmd == 'downgrade':
        command.downgrade(cfg, rev or '-1')
    else:
        print('Unsupported command')
        raise SystemExit(2)
