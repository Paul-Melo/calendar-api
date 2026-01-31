from flask import Blueprint, request, jsonify
from src.models.user import db, User, Appointment
from datetime import datetime

user_bp = Blueprint('user_bp', __name__)

@user_bp.route('/users', methods=['POST'])
def create_user():
    """Criar um novo usuário"""
    data = request.get_json()
    
    if not data or not data.get('name') or not data.get('email'):
        return jsonify({'error': 'Nome e email são obrigatórios'}), 400
    
    # Verificar se o usuário já existe
    existing_user = User.query.filter_by(email=data['email']).first()
    if existing_user:
        return jsonify({'error': 'Usuário já existe com este email'}), 409
    
    user = User(
        name=data['name'],
        email=data['email'],
        phone=data.get('phone')
    )
    
    try:
        db.session.add(user)
        db.session.commit()
        return jsonify({
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'phone': user.phone,
            'created_at': user.created_at.isoformat()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Erro ao criar usuário'}), 500

@user_bp.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """Obter informações de um usuário"""
    user = User.query.get_or_404(user_id)
    return jsonify({
        'id': user.id,
        'name': user.name,
        'email': user.email,
        'phone': user.phone,
        'created_at': user.created_at.isoformat()
    })

@user_bp.route('/appointments', methods=['POST'])
def create_appointment():
    """Criar um novo agendamento"""
    data = request.get_json()
    
    required_fields = ['user_id', 'appointment_date', 'service_type']
    if not data or not all(field in data for field in required_fields):
        return jsonify({'error': 'Campos obrigatórios: user_id, appointment_date, service_type'}), 400
    
    # Verificar se o usuário existe
    user = User.query.get(data['user_id'])
    if not user:
        return jsonify({'error': 'Usuário não encontrado'}), 404
    
    try:
        appointment_date = datetime.fromisoformat(data['appointment_date'].replace('Z', '+00:00'))
    except ValueError:
        return jsonify({'error': 'Formato de data inválido. Use ISO 8601'}), 400
    
    appointment = Appointment(
        user_id=data['user_id'],
        appointment_date=appointment_date,
        service_type=data['service_type'],
        google_event_id=data.get('google_event_id')
    )
    
    try:
        db.session.add(appointment)
        db.session.commit()
        return jsonify({
            'id': appointment.id,
            'user_id': appointment.user_id,
            'appointment_date': appointment.appointment_date.isoformat(),
            'service_type': appointment.service_type,
            'status': appointment.status,
            'google_event_id': appointment.google_event_id,
            'created_at': appointment.created_at.isoformat()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Erro ao criar agendamento'}), 500

@user_bp.route('/appointments/<int:appointment_id>', methods=['GET'])
def get_appointment(appointment_id):
    """Obter informações de um agendamento"""
    appointment = Appointment.query.get_or_404(appointment_id)
    return jsonify({
        'id': appointment.id,
        'user_id': appointment.user_id,
        'appointment_date': appointment.appointment_date.isoformat(),
        'service_type': appointment.service_type,
        'status': appointment.status,
        'google_event_id': appointment.google_event_id,
        'created_at': appointment.created_at.isoformat(),
        'user': {
            'name': appointment.user.name,
            'email': appointment.user.email,
            'phone': appointment.user.phone
        }
    })

@user_bp.route('/appointments', methods=['GET'])
def list_appointments():
    """Listar todos os agendamentos"""
    appointments = Appointment.query.order_by(Appointment.appointment_date.desc()).all()
    return jsonify([{
        'id': appointment.id,
        'user_id': appointment.user_id,
        'appointment_date': appointment.appointment_date.isoformat(),
        'service_type': appointment.service_type,
        'status': appointment.status,
        'google_event_id': appointment.google_event_id,
        'created_at': appointment.created_at.isoformat(),
        'user': {
            'name': appointment.user.name,
            'email': appointment.user.email,
            'phone': appointment.user.phone
        }
    } for appointment in appointments])

@user_bp.route('/contact', methods=['POST'])
def contact_form():
    """Processar formulário de contato"""
    data = request.get_json()
    
    required_fields = ['name', 'email', 'message']
    if not data or not all(field in data for field in required_fields):
        return jsonify({'error': 'Campos obrigatórios: name, email, message'}), 400
    
    # Aqui você pode implementar o envio de email ou salvar no banco
    # Por enquanto, apenas retornamos sucesso
    return jsonify({
        'message': 'Mensagem enviada com sucesso! Entraremos em contato em breve.',
        'data': {
            'name': data['name'],
            'email': data['email'],
            'phone': data.get('phone'),
            'message': data['message']
        }
    }), 200

