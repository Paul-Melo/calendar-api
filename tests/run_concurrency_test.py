"""Script standalone para testar concorrência no endpoint de agendamento.
Este script não depende do pytest e pode ser executado com:

    py -3 tests\run_concurrency_test.py

Ele usa o test_client do Flask e thread para simular duas requisições concorrentes.
"""
import threading
import time
import json
import os
import sys

# Garantir que o diretório do pacote `src` esteja no sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import types

# Criar módulos falsos para dependências do Google caso não estejam instaladas
google_modules = [
    'google_auth_oauthlib.flow',
    'google.oauth2.credentials',
    'googleapiclient.discovery',
    'googleapiclient.errors'
]
for mod in google_modules:
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

# Forçar objetos mínimos usados pelo código (Flow, Credentials, build, HttpError)
setattr(sys.modules['google_auth_oauthlib.flow'], 'Flow', object)
setattr(sys.modules['google.oauth2.credentials'], 'Credentials', object)
setattr(sys.modules['googleapiclient.discovery'], 'build', lambda *a, **k: None)
class _HttpError(Exception):
    pass
setattr(sys.modules['googleapiclient.errors'], 'HttpError', _HttpError)

from src.models.user import db, OAuthCredential, Appointment, User
from main import app
import src.routes.calendar as calendar_module


def make_client_with_session():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['oauth_credential_id'] = 1
    return client


class FakeEvents:
    def __init__(self, result):
        self._result = result

    def insert(self, calendarId, body):
        class Inserter:
            def __init__(self, result):
                self._result = result

            def execute(self):
                return self._result

        return Inserter(self._result)


class FakeService:
    def __init__(self, result):
        self._events = FakeEvents(result)

    def events(self):
        return self._events


def setup_db():
    with app.app_context():
        db.drop_all()
        db.create_all()
        cred = OAuthCredential(client_id='test', token='t', refresh_token='r', token_uri='u', scopes='["scope"]')
        db.session.add(cred)
        db.session.commit()


def do_concurrent_test():
    payload = {
        'name': 'Concorrente',
        'email': 'conc@example.com',
        'phone': '99999999',
        'date': '2025-12-01',
        'time': '09:00',
        'service_type': 'individual'
    }

    fake_event_result = {
        'id': 'evt-123',
        'htmlLink': 'https://example.com/event/evt-123',
        'start': {'dateTime': '2025-12-01T09:00:00'},
        'end': {'dateTime': '2025-12-01T09:50:00'}
    }

    # Monkeypatch build
    calendar_module.build = lambda name, version, credentials=None: FakeService(fake_event_result)
    # Monkeypatch get_credentials para evitar reconstrução de Credentials
    calendar_module.get_credentials = lambda: object()

    results = []

    def do_request(results_list):
        client = make_client_with_session()
        resp = client.post('/calendar/schedule_appointment', json=payload)
        try:
            body = resp.get_json()
        except Exception:
            body = resp.data.decode('utf-8')
        results_list.append((resp.status_code, body))

    t1 = threading.Thread(target=do_request, args=(results,))
    t2 = threading.Thread(target=do_request, args=(results,))

    t1.start()
    time.sleep(0.05)
    t2.start()

    t1.join()
    t2.join()

    print('Resultados:')
    for st, body in results:
        print('-', st, body)

    statuses = sorted(r[0] for r in results)
    success = any(s in (200, 201) for s in statuses)
    conflict = 409 in statuses

    if success and conflict:
        print('\nTeste de concorrência: OK (um sucesso + um conflito)')
        return 0
    else:
        print('\nTeste de concorrência: FALHOU')
        return 2


if __name__ == '__main__':
    setup_db()
    code = do_concurrent_test()
    raise SystemExit(code)
