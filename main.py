import os
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
from flask_session import Session as FlaskSession
import redis as redis_lib
from src.models.user import db
from src.routes.user import user_bp
from src.routes.calendar import calendar_bp

# Permitir OAuth inseguro em ambiente de desenvolvimento (apenas para testes locais)
# Define antes de importar/usar qualquer código que invoque a biblioteca oauthlib
if os.environ.get('FLASK_ENV') != 'production':
    os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))

# Configurações de segurança
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Session / Cookie security defaults for production
# Use Redis-backed server-side sessions when REDIS_URL is provided
redis_url = os.environ.get('REDIS_URL')
if redis_url:
    try:
        redis_client = redis_lib.from_url(redis_url)
        app.config['SESSION_TYPE'] = 'redis'
        app.config['SESSION_REDIS'] = redis_client
        app.config['SESSION_PERMANENT'] = False
        # Ensure cookies are secure in production; can be overridden via env vars
        app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', '1') == '1'
        app.config['SESSION_COOKIE_HTTPONLY'] = os.environ.get('SESSION_COOKIE_HTTPONLY', '1') == '1'
        app.config['SESSION_COOKIE_SAMESITE'] = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
        FlaskSession(app)
    except Exception as e:
        print(f"Aviso: falha ao conectar no Redis para sessão: {e}")
else:
    # If no Redis provided, ensure cookie flags are still secure by default
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'
    app.config['SESSION_COOKIE_HTTPONLY'] = os.environ.get('SESSION_COOKIE_HTTPONLY', '1') == '1'
    app.config['SESSION_COOKIE_SAMESITE'] = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')

# Configuração de CORS restrita
cors_origins = os.environ.get('CORS_ORIGINS', 'http://localhost:5173').split(',')
CORS(app, origins=cors_origins, supports_credentials=True)

# Inicializar banco de dados
db.init_app(app)

# Registrar blueprints
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(calendar_bp, url_prefix='/calendar')

# Criar tabelas
with app.app_context():
    os.makedirs('database', exist_ok=True)
    db.create_all()

@app.route('/health')
def health_check():
    """Endpoint de verificação de saúde"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(),
        'version': '2.0.0'
    })

@app.route('/api/contact', methods=['POST'])
def contact():
    """Endpoint para formulário de contato"""
    try:
        data = request.get_json()
        
        # Validação básica
        required_fields = ['name', 'email', 'message']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Campo {field} é obrigatório'}), 400
        
        # Aqui você pode implementar o envio de email
        # Por enquanto, apenas log
        print(f"Contato recebido: {data['name']} - {data['email']}")
        print(f"Mensagem: {data['message']}")
        
        return jsonify({'message': 'Mensagem enviada com sucesso!'}), 200
        
    except Exception as e:
        print(f"Erro no contato: {e}")
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    """Servir arquivos estáticos"""
    static_folder_path = app.static_folder
    if static_folder_path is None:
        return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

