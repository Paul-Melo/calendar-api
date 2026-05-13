from flask import Blueprint, request, redirect, url_for, session, jsonify, current_app
from src.models.user import db, User, Appointment, OAuthCredential

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

import os
import json
import urllib.parse
import traceback

calendar_bp = Blueprint("calendar_bp", __name__)

# Configurações do OAuth 2.0
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly"
]

# Configuração via variáveis de ambiente
CLIENT_CONFIG = None

if os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"):
    CLIENT_CONFIG = {
        "web": {
            "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
            "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }

# Timezone Brasil
BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")


def log_error(context, error):
    print(f"\n===== {context} =====")
    print(str(error))
    traceback.print_exc()
    print("=====================\n")


def get_credentials():
    """
    Obtém credenciais salvas no banco e faz refresh automático.
    """

    cred = OAuthCredential.query.order_by(OAuthCredential.id.desc()).first()

    if not cred:
        return None

    try:
        credentials = Credentials(
            token=cred.get_decrypted_token(),
            refresh_token=cred.refresh_token,
            token_uri=cred.token_uri,
            client_id=cred.client_id,
            client_secret=cred.client_secret,
            scopes=json.loads(cred.scopes) if cred.scopes else []
        )

        # Refresh automático
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())

            cred.set_encrypted_token(credentials.token)

            if credentials.expiry:
                cred.expires_at = credentials.expiry

            db.session.commit()

        return credentials

    except Exception as e:
        log_error("GET CREDENTIALS ERROR", e)
        db.session.rollback()
        return None


@calendar_bp.route("/authorize")
def authorize():
    """Iniciar OAuth"""

    try:

        if CLIENT_CONFIG is None:
            return jsonify({
                "error": "Credenciais Google não configuradas"
            }), 503

        redirect_uri = os.getenv(
            "GOOGLE_REDIRECT_URI",
            "https://api.cognitivatcc.com.br/calendar/oauth2callback"
        )

        print("===== GOOGLE OAUTH DEBUG =====")
        print("REDIRECT URI:", redirect_uri)
        print("CLIENT ID:", os.environ.get("GOOGLE_CLIENT_ID"))
        print("==============================")

        flow = Flow.from_client_config(
            CLIENT_CONFIG,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )

        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes=True,
            prompt="consent"
        )

        session["oauth_state"] = state
        session.modified = True

        return redirect(authorization_url)

    except Exception as e:

        log_error("AUTHORIZE ERROR", e)

        return jsonify({
            "error": str(e),
            "type": str(type(e))
        }), 500


@calendar_bp.route("/oauth2callback")
def oauth2callback():
    """Callback OAuth"""

    try:
        state = session.get("oauth_state")

        if not state:
            return jsonify({
                "error": "Sessão OAuth expirada"
            }), 400

        if CLIENT_CONFIG is None:
            return jsonify({
                "error": "Credenciais Google não configuradas"
            }), 503

        flow = Flow.from_client_config(
            CLIENT_CONFIG,
            scopes=SCOPES,
            state=state,
            redirect_uri=url_for("calendar_bp.oauth2callback", _external=True)
        )

        flow.fetch_token(authorization_response=request.url)

        credentials = flow.credentials

        try:
            cred = OAuthCredential.query.first()

            if not cred:
                cred = OAuthCredential()

            cred.client_id = credentials.client_id
            cred.refresh_token = credentials.refresh_token
            cred.token_uri = credentials.token_uri
            cred.client_secret = credentials.client_secret
            cred.scopes = json.dumps(list(credentials.scopes)) if credentials.scopes else None
            cred.expires_at = getattr(credentials, "expiry", None)

            cred.set_encrypted_token(credentials.token)

            db.session.add(cred)
            db.session.commit()

            session["oauth_credential_id"] = cred.id
            session.modified = True

        except Exception as e:
            db.session.rollback()

            return jsonify({
                "error": f"Falha ao persistir credenciais: {str(e)}"
            }), 500

        frontend_url = os.getenv(
            "FRONTEND_URL",
            "https://cognitivatcc.com.br"
        )

        return redirect(f"{frontend_url}?google_auth=success")

    except Exception as e:
        log_error("OAUTH CALLBACK ERROR", e)

        return jsonify({
            "error": f"Erro no callback OAuth: {str(e)}"
        }), 500


@calendar_bp.route("/debug_session", methods=["GET"])
def debug_session():
    """Debug da sessão"""

    try:
        sess = {
            k: (
                v if isinstance(v, (str, int, float, bool, type(None)))
                else str(v)
            )
            for k, v in session.items()
        }

        return jsonify({
            "session": sess
        }), 200

    except Exception as e:
        log_error("DEBUG SESSION ERROR", e)

        return jsonify({
            "error": "Erro ao ler sessão"
        }), 500


@calendar_bp.route("/available_slots", methods=["POST"])
def get_available_slots():
    """
    Obter horários disponíveis dinamicamente.
    """

    try:
        credentials = get_credentials()

        if not credentials:
            return jsonify({
                "error": "Agenda indisponível",
                "fallback": "whatsapp"
            }), 503

        service = build("calendar", "v3", credentials=credentials)

        data = request.get_json(silent=True) or {}

        date = data.get("date")
        service_type = data.get("service_type")  # presencial | online | teste

        if not date or not service_type:
            return jsonify({
                "error": "Parâmetros obrigatórios"
            }), 400

        # Tipos válidos
        valid_types = ["presencial", "online", "teste"]

        if service_type not in valid_types:
            return jsonify({
                "error": "Tipo de serviço inválido"
            }), 400

        duration_map = {
            "presencial": 50,
            "online": 50,
            "teste": 50
        }

        minutes = duration_map.get(service_type, 50)

        slot_duration = timedelta(minutes=minutes)
        buffer_duration = timedelta(minutes=10)

        # Horário de trabalho
        start_time = datetime.fromisoformat(
            f"{date}T09:00:00"
        ).replace(tzinfo=BRAZIL_TZ)

        end_time = datetime.fromisoformat(
            f"{date}T18:00:00"
        ).replace(tzinfo=BRAZIL_TZ)

        now = datetime.now(BRAZIL_TZ)

        freebusy_result = service.freebusy().query(
            body={
                "timeMin": start_time.isoformat(),
                "timeMax": end_time.isoformat(),
                "timeZone": "America/Sao_Paulo",
                "items": [{"id": "primary"}]
            }
        ).execute()

        busy_periods = freebusy_result["calendars"]["primary"].get("busy", [])

        normalized_busy = []

        for busy in busy_periods:
            b_start = datetime.fromisoformat(
                busy["start"].replace("Z", "+00:00")
            ).astimezone(BRAZIL_TZ)

            b_end = datetime.fromisoformat(
                busy["end"].replace("Z", "+00:00")
            ).astimezone(BRAZIL_TZ)

            normalized_busy.append((b_start, b_end))

        step = slot_duration + buffer_duration
        current = start_time

        # Intervalo almoço
        lunch_start = datetime.fromisoformat(
            f"{date}T12:00:00"
        ).replace(tzinfo=BRAZIL_TZ)

        lunch_end = datetime.fromisoformat(
            f"{date}T13:00:00"
        ).replace(tzinfo=BRAZIL_TZ)

        available_slots = []

        while current + slot_duration <= end_time:

            if current < now:
                current += step
                continue

            proposed_end = current + slot_duration

            conflict = any(
                current < b_end and proposed_end > b_start
                for b_start, b_end in normalized_busy
            )

            buffer_conflict = any(
                proposed_end < b_end and
                (proposed_end + buffer_duration) > b_start
                for b_start, b_end in normalized_busy
            )

            overlaps_lunch = not (
                proposed_end <= lunch_start or current >= lunch_end
            )

            if not conflict and not buffer_conflict and not overlaps_lunch:
                available_slots.append({
                    "start": current.strftime("%H:%M"),
                    "end": proposed_end.strftime("%H:%M"),
                    "datetime": current.isoformat()
                })

            current += step

        return jsonify({
            "date": date,
            "available_slots": available_slots
        })

    except Exception as e:
        log_error("AVAILABLE SLOTS ERROR", e)

        return jsonify({
            "error": "Erro ao buscar horários"
        }), 500


@calendar_bp.route("/schedule_appointment", methods=["POST"])
def schedule_appointment():
    """
    Agendar consulta.
    """

    try:
        credentials = get_credentials()

        if not credentials:
            return jsonify({
                "error": "Google Calendar não conectado",
                "fallback": "whatsapp"
            }), 503

        data = request.get_json(silent=True) or {}

        required_fields = [
            "name",
            "email",
            "phone",
            "date",
            "time",
            "service_type"
        ]

        if not all(field in data for field in required_fields):
            return jsonify({
                "error": "Todos os campos são obrigatórios"
            }), 400

        # Tipos válidos
        valid_types = ["presencial", "online", "teste"]

        if data["service_type"] not in valid_types:
            return jsonify({
                "error": "Tipo de serviço inválido"
            }), 400

        start_datetime = datetime.fromisoformat(
            f"{data['date']}T{data['time']}:00"
        ).replace(tzinfo=BRAZIL_TZ)

        duration_map = {
            "presencial": 50,
            "online": 50,
            "teste": 50
        }

        minutes = duration_map.get(data["service_type"], 50)

        end_datetime = start_datetime + timedelta(minutes=minutes)

        service_types = {
            "presencial": "Consulta Presencial",
            "online": "Consulta Online",
            "teste": "Teste de Serviço"
        }

        service_name = service_types.get(
            data["service_type"],
            "Consulta"
        )

        # Reservar horário no banco
        try:
            with db.session.begin():

                existing = Appointment.query.filter_by(
                    appointment_date=start_datetime,
                    service_type=data["service_type"]
                ).first()

                if existing:
                    return jsonify({
                        "error": "Este horário já foi agendado"
                    }), 409

                user = User.query.filter_by(
                    email=data["email"]
                ).first()

                if not user:
                    user = User(
                        name=data["name"],
                        email=data["email"],
                        phone=data["phone"]
                    )

                    db.session.add(user)
                    db.session.flush()

                appointment = Appointment(
                    user_id=user.id,
                    appointment_date=start_datetime,
                    service_type=data["service_type"],
                    google_event_id=None
                )

                db.session.add(appointment)
                db.session.flush()

                reserved_id = appointment.id

        except IntegrityError:
            db.session.rollback()

            return jsonify({
                "error": "Conflito ao reservar horário"
            }), 409

        service = build("calendar", "v3", credentials=credentials)

        event = {
            "summary": f"{service_name} - {data['name']}",
            "location": (
                "Online"
                if data["service_type"] == "online"
                else "Consultório - Rua Halfeld 414/1001, Centro, Juiz de Fora-MG"
            ),
            "description": (
                f"Sessão TCC\n\n"
                f"Paciente: {data['name']}\n"
                f"Telefone: {data['phone']}\n"
                f"Email: {data['email']}\n"
                f"Tipo: {service_name}\n\n"
                f"Observações: {data.get('message', 'Nenhuma observação')}"
            ),
            "start": {
                "dateTime": start_datetime.isoformat(),
                "timeZone": "America/Sao_Paulo"
            },
            "end": {
                "dateTime": end_datetime.isoformat(),
                "timeZone": "America/Sao_Paulo"
            },
            "attendees": [
                {"email": data["email"]}
            ],
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 1440},
                    {"method": "email", "minutes": 120},
                    {"method": "popup", "minutes": 10}
                ]
            }
        }

        try:
            created_event = service.events().insert(
                calendarId="primary",
                body=event
            ).execute()

        except HttpError as e:

            try:
                with db.session.begin():
                    ap = Appointment.query.get(reserved_id)

                    if ap:
                        db.session.delete(ap)

            except Exception:
                db.session.rollback()

            log_error("GOOGLE EVENT ERROR", e)

            return jsonify({
                "error": "Erro ao criar evento no Google Calendar",
                "fallback": "whatsapp"
            }), 500

        # Atualizar agendamento com ID Google
        try:
            with db.session.begin():

                ap = Appointment.query.get(reserved_id)

                if not ap:
                    try:
                        service.events().delete(
                            calendarId="primary",
                            eventId=created_event["id"]
                        ).execute()

                    except Exception:
                        pass

                    return jsonify({
                        "error": "Erro ao confirmar agendamento"
                    }), 500

                ap.google_event_id = created_event["id"]

                db.session.add(ap)

        except IntegrityError:
            db.session.rollback()

            try:
                service.events().delete(
                    calendarId="primary",
                    eventId=created_event["id"]
                ).execute()

            except Exception:
                pass

            return jsonify({
                "error": "Erro ao salvar agendamento"
            }), 500

        # Buscar dados finais
        user_db = User.query.get(user.id)
        ap = Appointment.query.get(reserved_id)

        if not user_db or not ap:
            return jsonify({
                "error": "Erro ao finalizar agendamento"
            }), 500

        # WhatsApp
        numero = os.getenv("NUMERO_WHATSAPP")

        if not numero:
            return jsonify({
                "error": "NUMERO_WHATSAPP não configurado"
            }), 500

        mensagem = f"""
Olá! Acabei de agendar uma consulta.

📅 Data: {data.get('date', 'N/A')}
⏰ Horário: {data.get('time', 'N/A')}
📍 Tipo: {service_name}

Poderia confirmar, por favor? 😊
"""

        whatsapp_url = (
            f"https://wa.me/{numero}"
            f"?text={urllib.parse.quote(mensagem)}"
        )

        return jsonify({
            "message": "Agendamento realizado com sucesso!",
            "appointment": {
                "event_id": created_event.get("id"),
                "html_link": created_event.get("htmlLink"),
                "start": created_event.get("start"),
                "end": created_event.get("end"),
                "patient_name": user_db.name,
                "patient_email": user_db.email,
                "service_type": service_name,
                "duration_minutes": minutes,
                "location": event.get("location"),
                "local_id": ap.id
            },
            "whatsapp_link": whatsapp_url
        })

    except Exception as e:
        log_error("SCHEDULE APPOINTMENT ERROR", e)

        return jsonify({
            "error": "Erro temporário no sistema",
            "fallback": "whatsapp"
        }), 500


@calendar_bp.route("/auth_status", methods=["GET"])
def auth_status():
    """
    Status autenticação Google.
    """

    try:
        credentials = get_credentials()

        if not credentials:
            return jsonify({
                "authenticated": False,
                "status": "not_connected",
                "message": "Google Calendar não conectado"
            })

        service = build("calendar", "v3", credentials=credentials)

        service.calendarList().list().execute()

        return jsonify({
            "authenticated": True,
            "status": "connected",
            "message": "Google Calendar conectado"
        })

    except Exception as e:
        log_error("AUTH STATUS ERROR", e)

        return jsonify({
            "authenticated": False,
            "status": "expired",
            "message": "Credenciais expiradas"
        })


@calendar_bp.route("/debug/fallback_on", methods=["GET"])
def debug_fallback_on():

    if not (current_app and current_app.debug):
        return jsonify({
            "error": "Disponível somente em debug"
        }), 403

    session["use_dev_fallback"] = True

    return jsonify({
        "message": "Fallback ativado"
    })


@calendar_bp.route("/debug/fallback_off", methods=["GET"])
def debug_fallback_off():

    if not (current_app and current_app.debug):
        return jsonify({
            "error": "Disponível somente em debug"
        }), 403

    session.pop("use_dev_fallback", None)

    return jsonify({
        "message": "Fallback desativado"
    })


@calendar_bp.route("/logout", methods=["POST"])
def logout():
    """
    Logout.
    """

    session.clear()

    return jsonify({
        "message": "Logout realizado com sucesso"
    })


@calendar_bp.route("/admin/connect", methods=["GET"])
def admin_connect():
    """
    Painel admin conexão Google.
    """

    auth_response = auth_status()
    status_data = auth_response.get_json()

    if status_data["authenticated"]:
        return jsonify({
            "status": "connected",
            "message": "Google Calendar conectado",
            "actions": {
                "test": "/calendar/admin/test",
                "disconnect": "/calendar/logout"
            }
        })

    return jsonify({
        "status": "not_connected",
        "message": "Google Calendar não conectado",
        "actions": {
            "connect": "/calendar/authorize"
        }
    })


@calendar_bp.route("/admin/test", methods=["GET"])
def admin_test():
    """
    Testar integração Google Calendar.
    """

    try:
        credentials = get_credentials()

        if not credentials:
            return jsonify({
                "error": "Não autenticado"
            }), 401

        service = build("calendar", "v3", credentials=credentials)

        calendar_list = service.calendarList().list().execute()

        today = datetime.now(BRAZIL_TZ).date()

        start_time = datetime.combine(
            today,
            datetime.min.time()
        ).replace(tzinfo=BRAZIL_TZ)

        end_time = start_time + timedelta(days=1)

        events_result = service.events().list(
            calendarId="primary",
            timeMin=start_time.isoformat(),
            timeMax=end_time.isoformat(),
            maxResults=10,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])

        return jsonify({
            "status": "success",
            "message": "Integração funcionando corretamente",
            "data": {
                "calendars_count": len(calendar_list.get("items", [])),
                "events_today": len(events),
                "timezone": "America/Sao_Paulo"
            }
        })

    except Exception as e:
        log_error("ADMIN TEST ERROR", e)

        return jsonify({
            "status": "error",
            "message": f"Erro na integração: {str(e)}"
        }), 500