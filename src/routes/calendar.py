from flask import Blueprint, request, redirect, url_for, session, jsonify, current_app
from src.models.user import db, User, Appointment, OAuthCredential
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import json
from sqlalchemy.exc import IntegrityError

calendar_bp = Blueprint("calendar_bp", __name__)

# Configurações do OAuth 2.0
SCOPES = ["https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar.readonly"]

# Suporte a configuração via variáveis de ambiente (mais seguro para produção).
# Em produção, `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` devem ser definidos.
# Não existe fallback para `client_secret.json` para evitar vazamento de segredos.
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

# Timezone do Brasil
BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")

def get_credentials():
    """Recupera credenciais a partir do banco usando `oauth_credential_id` na sessão.

    Se necessário, realiza refresh e persiste os tokens atualizados no DB.
    """
    cred_id = session.get('oauth_credential_id')
    if not cred_id:
        return None

    cred_obj = OAuthCredential.query.get(cred_id)
    if not cred_obj:
        session.pop('oauth_credential_id', None)
        return None

    credentials = Credentials(**cred_obj.to_credentials_dict())
    # Refresh automático se expirado e refresh_token disponível
    if credentials.expired and credentials.refresh_token:
        try:
            from google.auth.transport.requests import Request
            credentials.refresh(Request())
            # Persistir tokens atualizados no DB (usar encriptação quando disponível)
            try:
                cred_obj.set_encrypted_token(credentials.token)
            except Exception:
                cred_obj.token = credentials.token
            cred_obj.refresh_token = credentials.refresh_token
            cred_obj.token_uri = credentials.token_uri
            cred_obj.scopes = json.dumps(list(credentials.scopes)) if credentials.scopes else None
            if getattr(credentials, 'expiry', None):
                cred_obj.expires_at = credentials.expiry
            db.session.commit()
        except Exception:
            # Remover credencial inválida
            try:
                db.session.delete(cred_obj)
                db.session.commit()
            except Exception:
                db.session.rollback()
            session.pop('oauth_credential_id', None)
            return None
    return credentials

@calendar_bp.route("/authorize")
def authorize():
    """Iniciar processo de autorização OAuth 2.0"""
    try:
        # Preferir credenciais via variáveis de ambiente (segurança)
        if CLIENT_CONFIG is not None:
            flow = Flow.from_client_config(
                CLIENT_CONFIG,
                scopes=SCOPES,
                redirect_uri=url_for("calendar_bp.oauth2callback", _external=True)
            )
        else:
            # Em produção não existe fallback para arquivo local. Solicitar
            # configuração via variáveis de ambiente.
            return jsonify({
                "error": "Credenciais do Google não configuradas. Defina GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET.",
                "admin_required": True
            }), 503

        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )

        session["oauth_state"] = state
        return redirect(authorization_url)
    except Exception as e:
        return jsonify({"error": f"Erro na autorização: {str(e)}"}), 500

@calendar_bp.route("/oauth2callback")
def oauth2callback():
    """Callback do OAuth 2.0"""
    try:
        state = session.get("oauth_state")
        if not state:
            return jsonify({"error": "Estado OAuth não encontrado"}), 400

        if CLIENT_CONFIG is not None:
            flow = Flow.from_client_config(
                CLIENT_CONFIG,
                scopes=SCOPES,
                state=state,
                redirect_uri=url_for("calendar_bp.oauth2callback", _external=True)
            )
        else:
            return jsonify({
                "error": "Credenciais do Google não configuradas. Defina GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET.",
                "admin_required": True
            }), 503

        flow.fetch_token(authorization_response=request.url)

        credentials = flow.credentials
        # Persistir credenciais no banco em vez de na sessão
        try:
            cred = OAuthCredential(
                client_id=credentials.client_id,
                refresh_token=credentials.refresh_token,
                token_uri=credentials.token_uri,
                scopes=json.dumps(list(credentials.scopes)) if credentials.scopes else None,
                expires_at=getattr(credentials, 'expiry', None)
            )
            # tentar encriptar token ao salvar
            try:
                cred.set_encrypted_token(credentials.token)
            except Exception:
                cred.token = credentials.token

            db.session.add(cred)
            db.session.commit()
            # Armazenar apenas o identificador curto na sessão
            session['oauth_credential_id'] = cred.id
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": f"Falha ao persistir credenciais: {e}"}), 500

        return jsonify({"message": "Autenticação bem-sucedida!"})
    except Exception as e:
        return jsonify({"error": f"Erro no callback OAuth: {str(e)}"}), 500

@calendar_bp.route("/available_slots", methods=["POST"])
def get_available_slots():
    """Obter horários disponíveis dinamicamente de acordo com o tipo de serviço.
        Regras:
        - Duração: premium 80 min, individual/online 50 min.
        - Buffer padrão entre sessões: 10 min.
        - Geração: avalia início em passos iguais a (duração + buffer),
            por exemplo 50min + 10min = 60min (intervalo de 1 hora) entre 09:00 e 18:00.
        - Filtra contra períodos ocupados da FreeBusy API.
    """
    # Requer usuário autenticado com credenciais na sessão em produção.
    if "oauth_credential_id" not in session:
        return jsonify({
            "error": "Sistema de agendamento indisponível. Conecte o Google Calendar.",
            "admin_required": True
        }), 401
    busy_periods = None

    try:
        credentials = get_credentials()
        if not credentials:
            return jsonify({
                "error": "Sessão expirada. Reconecte o Google Calendar.",
                "fallback": "whatsapp"
            }), 401
        service = build("calendar", "v3", credentials=credentials)

        data = request.json or {}
        print('[DEBUG] /calendar/available_slots called with:', data)
        date = data.get('date')  # Formato: YYYY-MM-DD
        service_type = data.get('service_type')  # individual | online | premium

        if not date:
            return jsonify({"error": "Data é obrigatória"}), 400
        if not service_type:
            return jsonify({"error": "Tipo de serviço é obrigatório"}), 400

        duration_map = {
            'premium': 80,
            'individual': 50,
            'online': 50
        }
        minutes = duration_map.get(service_type, 50)
        slot_duration = timedelta(minutes=minutes)
        buffer_duration = timedelta(minutes=10)

        # Janela de trabalho
        start_time = datetime.fromisoformat(f"{date}T09:00:00").replace(tzinfo=BRAZIL_TZ)
        end_time = datetime.fromisoformat(f"{date}T18:00:00").replace(tzinfo=BRAZIL_TZ)

        # FreeBusy consulta
        freebusy_request = {
            "timeMin": start_time.isoformat(),
            "timeMax": end_time.isoformat(),
            "timeZone": "America/Sao_Paulo",
            "items": [{"id": "primary"}]
        }
        # Se já temos busy_periods (fallback), pular chamada externa
        if busy_periods is None:
            freebusy_result = service.freebusy().query(body=freebusy_request).execute()
            busy_periods = freebusy_result["calendars"]["primary"].get("busy", [])
            print(f"[DEBUG] FreeBusy returned {len(busy_periods)} busy periods")
            # print busy periods truncated
            for bp in busy_periods[:10]:
                print('[DEBUG] busy:', bp)

        # Normalizar períodos ocupados para comparação
        normalized_busy = []
        for busy in busy_periods:
            b_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
            b_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))
            if b_start.tzinfo is None:
                b_start = b_start.replace(tzinfo=BRAZIL_TZ)
            if b_end.tzinfo is None:
                b_end = b_end.replace(tzinfo=BRAZIL_TZ)
            normalized_busy.append((b_start, b_end))

        # Iterar em passos iguais a duração da sessão + buffer (ex.: 50 + 10 = 60min)
        # isso garante intervalos horários adequados quando a sessão tem duração
        # menor que a hora (por exemplo sessões de 50min => intervalos de 1h).
        step = slot_duration + buffer_duration
        available_slots = []
        current = start_time
        # Janela de almoço (bloqueada): 12:00 - 13:00
        lunch_start = datetime.fromisoformat(f"{date}T12:00:00").replace(tzinfo=BRAZIL_TZ)
        lunch_end = datetime.fromisoformat(f"{date}T13:00:00").replace(tzinfo=BRAZIL_TZ)
        while current + slot_duration <= end_time:
            proposed_end = current + slot_duration
            # Verificar conflitos (incluindo buffer no final para próxima sessão)
            has_conflict = False
            for b_start, b_end in normalized_busy:
                # conflito se intervalo cruza período ocupado
                if current < b_end and proposed_end > b_start:
                    has_conflict = True
                    break
            if not has_conflict:
                # Verificar também se adicionar buffer não cola em período ocupado seguinte
                buffer_end = proposed_end + buffer_duration
                conflict_buffer = False
                for b_start, b_end in normalized_busy:
                    if proposed_end < b_end and buffer_end > b_start:
                        conflict_buffer = True
                        break
                # Também bloquear período de almoço: se o slot proposto overlap com
                # lunch_start..lunch_end, ignorar (início ou fim dentro do almoço).
                overlaps_lunch = not (proposed_end <= lunch_start or current >= lunch_end)
                if not conflict_buffer and not overlaps_lunch:
                    available_slots.append({
                        'start': current.strftime('%H:%M'),
                        'end': proposed_end.strftime('%H:%M'),
                        'datetime': current.isoformat(),
                        'duration_minutes': minutes,
                        'service_type': service_type
                    })
            current += step

        print(f"[DEBUG] Generated {len(available_slots)} available slots for {service_type} ({minutes}min)")
        return jsonify({
            "date": date,
            "service_type": service_type,
            "duration_minutes": minutes,
            "available_slots": available_slots,
            "timezone": "America/Sao_Paulo"
        })

    except HttpError:
        return jsonify({
            "error": "Erro ao acessar calendário. Tente novamente ou entre em contato via WhatsApp.",
            "fallback": "whatsapp"
        }), 500
    except Exception:
        return jsonify({
            "error": "Erro temporário no sistema. Entre em contato via WhatsApp.",
            "fallback": "whatsapp"
        }), 500

@calendar_bp.route("/schedule_appointment", methods=["POST"])
def schedule_appointment():
    """Agendar consulta completa com transação idempotente"""
    if "oauth_credential_id" not in session:
        return jsonify({
            "error": "Sistema de agendamento temporariamente indisponível. Entre em contato via WhatsApp.",
            "fallback": "whatsapp"
        }), 401
    try:
        data = request.json

        # Validar dados
        required_fields = ['name', 'email', 'phone', 'date', 'time', 'service_type']
        if not data or not all(field in data for field in required_fields):
            return jsonify({"error": "Todos os campos são obrigatórios"}), 400

        # Preparar dados do evento com timezone correto
        start_datetime = datetime.fromisoformat(f"{data['date']}T{data['time']}:00").replace(tzinfo=BRAZIL_TZ)
        # Definir duração conforme tipo (premium 80 min, demais 50)
        duration_map = {
            'premium': 80,
            'individual': 50,
            'online': 50
        }
        minutes = duration_map.get(data['service_type'], 50)
        end_datetime = start_datetime + timedelta(minutes=minutes)

        # Mapear tipos de serviço
        service_types = {
            'individual': 'Terapia Individual',
            'online': 'Terapia Online',
            'premium': 'Sessão Premium'
        }
        service_name = service_types.get(data['service_type'], 'Consulta')

        # Primeiro, tentar reservar o horário no banco (transação)
        try:
            # Iniciar transação; commit será feito ao sair do bloco
            with db.session.begin():
                # Verificar se já existe agendamento para mesma data+serviço
                existing = Appointment.query.filter_by(appointment_date=start_datetime, service_type=data['service_type']).first()
                if existing:
                    return jsonify({"error": "Este horário já foi agendado. Por favor, escolha outro horário."}), 409

                # Criar ou obter usuário
                user = User.query.filter_by(email=data['email']).first()
                if not user:
                    user = User(name=data['name'], email=data['email'], phone=data['phone'])
                    db.session.add(user)
                    db.session.flush()

                # Inserir agendamento reservado (google_event_id será atualizado depois)
                appointment = Appointment(
                    user_id=user.id,
                    appointment_date=start_datetime,
                    service_type=data['service_type'],
                    google_event_id=None
                )
                db.session.add(appointment)
                db.session.flush()
                reserved_id = appointment.id
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "Conflito ao reservar horário. Por favor, escolha outro horário."}), 409

        # A partir daqui o horário está reservado no DB; criar o evento no Google
        credentials = get_credentials()
        if not credentials:
            # Limpar reserva local caso sessão inválida
            try:
                with db.session.begin():
                    ap = Appointment.query.get(reserved_id)
                    if ap:
                        db.session.delete(ap)
            except Exception:
                db.session.rollback()
            return jsonify({
                "error": "Sessão expirada. Reconecte o Google Calendar.",
                "fallback": "whatsapp"
            }), 401

        service = build("calendar", "v3", credentials=credentials)

        event = {
            "summary": f"{service_name} - {data['name']}",
            "location": "Online" if data['service_type'] == 'online' else "Consultório - Rua Halfeld 414/1001, Centro, Juiz de Fora-MG",
            "description": f"Sessão de Terapia Cognitivo-Comportamental\n\nPaciente: {data['name']}\nTelefone: {data['phone']}\nEmail: {data['email']}\nTipo: {service_name}\n\nObservações: {data.get('message', 'Nenhuma observação')}",
            "start": {
                "dateTime": start_datetime.isoformat(),
                "timeZone": "America/Sao_Paulo",
            },
            "end": {
                "dateTime": end_datetime.isoformat(),
                "timeZone": "America/Sao_Paulo",
            },
            "attendees": [
                {"email": data['email']},
            ],
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 24 * 60},
                    {"method": "email", "minutes": 2 * 60},
                    {"method": "popup", "minutes": 10},
                ],
            },
        }

        try:
            created_event = service.events().insert(calendarId='primary', body=event).execute()
        except HttpError as e:
            # Remover reserva local se falhar na criação do evento
            try:
                with db.session.begin():
                    ap = Appointment.query.get(reserved_id)
                    if ap:
                        db.session.delete(ap)
            except Exception:
                db.session.rollback()
            if "already exists" in str(e).lower():
                return jsonify({"error": "Este horário já foi agendado. Por favor, escolha outro horário."}), 409
            return jsonify({
                "error": "Erro ao criar evento no Google Calendar. Tente novamente.",
                "fallback": "whatsapp"
            }), 500

        # Atualizar o registro do agendamento com o ID do Google
        try:
            with db.session.begin():
                ap = Appointment.query.get(reserved_id)
                if not ap:
                    # Situação inesperada: registro não encontrado
                    # Tentar apagar o evento criado para não deixar órfão
                    try:
                        service.events().delete(calendarId='primary', eventId=created_event['id']).execute()
                    except Exception:
                        pass
                    return jsonify({"error": "Erro interno ao confirmar agendamento."}), 500
                ap.google_event_id = created_event['id']
                db.session.add(ap)
        except IntegrityError:
            db.session.rollback()
            # Em caso de falha ao atualizar DB, remover evento do Google
            try:
                service.events().delete(calendarId='primary', eventId=created_event['id']).execute()
            except Exception:
                pass
            return jsonify({"error": "Erro ao salvar agendamento no sistema. Tente novamente."}), 500
        # try:
        #     erp_response = requests.post(
        #         f"{ERP_BASE_URL}/api/appointments/",
        #         json={
        #             "google_event_id": created_event["id"],
        #             "patient_name": data['name'],
        #             "patient_email": data['email'],
        #             "patient_phone": data['phone'],
        #             "start_datetime": start_datetime.isoformat(),
        #             "end_datetime": end_datetime.isoformat(),
        #             "service_type": data['service_type']
        #         },
        #         headers={"Authorization": f"Bearer {ERP_TOKEN}"},
        #         timeout=5
        #     )
        #     erp_response.raise_for_status()
        # except Exception as erp_error:
        #     # Se falhar no ERP, apagar o evento do Google para evitar inconsistência
        #     service.events().delete(calendarId='primary', eventId=created_event["id"]).execute()
        #     raise Exception(f"Erro na integração com sistema interno: {erp_error}")
        
        # Responder com dados finais do agendamento
        user = User.query.get(user.id)
        ap = Appointment.query.get(reserved_id)
        return jsonify({
            "message": "Agendamento realizado com sucesso! Você receberá um email de confirmação em breve.",
            "appointment": {
                "event_id": created_event["id"],
                "html_link": created_event.get("htmlLink"),
                "start": created_event.get("start"),
                "end": created_event.get("end"),
                "patient_name": user.name,
                "patient_email": user.email,
                "service_type": service_name,
                "duration_minutes": minutes,
                "location": event["location"],
                "local_id": ap.id
            }
        })
    except Exception as e:
        return jsonify({
            "error": "Erro temporário no sistema. Entre em contato via WhatsApp.",
            "fallback": "whatsapp"
        }), 500

@calendar_bp.route("/auth_status", methods=["GET"])
def auth_status():
    """Verificar status de autenticação"""
    if "oauth_credential_id" in session:
        try:
            credentials = get_credentials()
            if not credentials:
                return jsonify({
                    "authenticated": False,
                    "status": "expired",
                    "message": "Credenciais expiradas"
                })
            service = build("calendar", "v3", credentials=credentials)
            service.calendarList().list().execute()
            
            return jsonify({
                "authenticated": True,
                "status": "connected",
                "message": "Google Calendar conectado"
            })
        except Exception:
            # Credenciais inválidas, limpar sessão
            session.clear()
            return jsonify({
                "authenticated": False,
                "status": "expired",
                "message": "Credenciais expiradas"
            })
    else:
        return jsonify({
            "authenticated": False,
            "status": "not_connected",
            "message": "Google Calendar não conectado"
        })


@calendar_bp.route('/debug/fallback_on', methods=['GET'])
def debug_fallback_on():
    """Ativa fallback de desenvolvimento que ignora credenciais e simula disponibilidade.
    Disponível apenas com app.debug == True.
    """
    if not (current_app and current_app.debug):
        return jsonify({"error": "Disponível somente em modo debug"}), 403
    session['use_dev_fallback'] = True
    return jsonify({"message": "Dev fallback ativado"})


@calendar_bp.route('/debug/fallback_off', methods=['GET'])
def debug_fallback_off():
    if not (current_app and current_app.debug):
        return jsonify({"error": "Disponível somente em modo debug"}), 403
    session.pop('use_dev_fallback', None)
    return jsonify({"message": "Dev fallback desativado"})

@calendar_bp.route("/logout", methods=["POST"])
def logout():
    """Fazer logout (limpar sessão)"""
    session.clear()
    return jsonify({"message": "Logout realizado com sucesso"})

@calendar_bp.route("/admin/connect", methods=["GET"])
def admin_connect():
    """Página administrativa para conectar Google Calendar"""
    auth_status_response = auth_status()
    status_data = auth_status_response.get_json()
    
    if status_data["authenticated"]:
        return jsonify({
            "status": "connected",
            "message": "Google Calendar já está conectado",
            "actions": {
                "test": "/calendar/admin/test",
                "disconnect": "/calendar/logout"
            }
        })
    else:
        return jsonify({
            "status": "not_connected",
            "message": "Google Calendar não está conectado",
            "actions": {
                "connect": "/calendar/authorize"
            }
        })

@calendar_bp.route("/admin/test", methods=["GET"])
def admin_test():
    """Testar integração com Google Calendar"""
    if "oauth_credential_id" not in session:
        return jsonify({"error": "Não autenticado"}), 401
    
    try:
        credentials = get_credentials()
        if not credentials:
            return jsonify({"error": "Sessão expirada"}), 401
        service = build("calendar", "v3", credentials=credentials)
        
        # Testar listagem de calendários
        calendar_list = service.calendarList().list().execute()
        
        # Testar busca de eventos hoje
        today = datetime.now(BRAZIL_TZ).date()
        start_time = datetime.combine(today, datetime.min.time()).replace(tzinfo=BRAZIL_TZ)
        end_time = start_time + timedelta(days=1)
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_time.isoformat(),
            timeMax=end_time.isoformat(),
            maxResults=10,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        return jsonify({
            "status": "success",
            "message": "Integração funcionando corretamente",
            "data": {
                "calendars_count": len(calendar_list.get('items', [])),
                "events_today": len(events),
                "timezone": "America/Sao_Paulo"
            }
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Erro na integração: {str(e)}"
        }), 500

