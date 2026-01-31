import threading
import time
import json
from flask import session
from src.models.user import db, OAuthCredential, Appointment, User
from main import app
import src.routes.calendar as calendar_module


def make_client_with_session():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['oauth_credential_id'] = 1
    return client


# Fake build/service to avoid calling Google API
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


def setup_module(module):
    # Configurar banco de teste (usa o mesmo DB configurado pelo app)
    with app.app_context():
        db.drop_all()
        db.create_all()
        # Criar um OAuthCredential fake para satisfazer checagem de sessão
        cred = OAuthCredential(client_id='test', token='t', refresh_token='r', token_uri='u', scopes='["scope"]')
        db.session.add(cred)
        db.session.commit()


def test_concurrent_schedule_requests(monkeypatch):
    payload = {
        'name': 'Concorrente',
        'email': 'conc@example.com',
        'phone': '99999999',
        'date': '2025-12-01',
        'time': '09:00',
        'service_type': 'individual'
    }

    # Mockar build para retornar serviço fake
    fake_event_result = {
        'id': 'evt-123',
        'htmlLink': 'https://example.com/event/evt-123',
        'start': {'dateTime': '2025-12-01T09:00:00'},
        'end': {'dateTime': '2025-12-01T09:50:00'}
    }
    monkeypatch.setattr(calendar_module, 'build', lambda name, version, credentials=None: FakeService(fake_event_result))

    results = []

    def do_request(results_list):
        client = make_client_with_session()
        resp = client.post('/calendar/schedule_appointment', json=payload)
        results_list.append((resp.status_code, resp.get_json()))

    # Rodar duas threads concorrentes
    t1 = threading.Thread(target=do_request, args=(results,))
    t2 = threading.Thread(target=do_request, args=(results,))

    t1.start()
    time.sleep(0.05)  # pequena defasagem para aumentar chance de conflito
    t2.start()

    t1.join()
    t2.join()

    # Devem existir duas respostas
    assert len(results) == 2
    statuses = sorted(r[0] for r in results)
    # Um deve ter sido 200/201 (sucesso) e outro 409 (conflito)
    assert 200 in statuses or 201 in statuses
    assert 409 in statuses


if __name__ == '__main__':
    import pytest
    pytest.main([__file__])
