import os
import sys
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

# Capturar e logar qualquer erro de importação inicial para facilitar debug no deploy
try:
    from src.models.user import db
    from src.routes.user import user_bp
    from src.routes.calendar import calendar_bp
except Exception:
    print("ERROR: falha ao importar módulos da aplicação durante startup.", file=sys.stderr)
    traceback.print_exc()
    # Re-raise para que o processo falhe visivelmente após log
    raise

# Permitir OAuth inseguro em ambiente de desenvolvimento (apenas para testes locais)
# Define antes de importar/usar qualquer código que invoque a biblioteca oauthlib
if os.environ.get('FLASK_ENV') != 'production':
    os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')

# Aplicação Flask
app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))

app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configurações de segurança e banco de dados
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')

# Preferir DATABASE_URL (ex.: Supabase/Postgres). Em ambientes de desenvolvimento,
# se DATABASE_URL não estiver setado, podemos usar um fallback para sqlite local.
database_url = os.environ.get('DATABASE_URL')
if not database_url and os.environ.get('FLASK_ENV') != 'production':
    local_db_path = os.path.join(os.path.dirname(__file__), 'database', 'app.db')
    database_url = f"sqlite:///{local_db_path}"

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Sessão padrão Flask via cookies seguros
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_DOMAIN'] = '.cognitivatcc.com.br'

# Configuração de CORS restrita
cors_origins = [
    origin.strip()
    for origin in os.environ.get(
        'CORS_ORIGINS',
        'http://localhost:5173,https://cognitivatcc.com.br,https://www.cognitivatcc.com.br'
    ).split(',')
]
CORS(app, origins=cors_origins, supports_credentials=True)
# Debug: log CORS origins configured (temporário)
print("CORS_ORIGINS =", cors_origins)

@app.before_request
def _log_request_origin():
    """Log the Origin header for calendar routes to help debug CORS issues (temporário)."""
    try:
        origin = request.headers.get('Origin')
        # Only log calendar-related requests to reduce noise
        if request.path.startswith('/calendar'):
            print(f"Request path={request.path} Origin={origin}")
    except Exception:
        pass

# Inicializar banco de dados
db.init_app(app)

# Registrar blueprints
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(calendar_bp, url_prefix='/calendar')

# Criar tabelas apenas para sqlite local (evitar criar/alterar schema em bancos gerenciados)
with app.app_context():
    db_url = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if db_url.startswith('sqlite'):
        # garantir pasta local de banco
        os.makedirs(os.path.join(os.path.dirname(__file__), 'database'), exist_ok=True)
        db.create_all()
    else:
        # Em ambientes com Postgres (Supabase) use Alembic para aplicar migrations
        pass

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
    # Use PORT set by platform (Render) when available; default to 5000 for local dev
    port = int(os.environ.get('PORT', 5000))
    is_production = os.environ.get('FLASK_ENV') == 'production'
    if is_production:
        print("Starting development server in PRODUCTION mode is not recommended. Use Gunicorn." )
    debug_mode = not is_production
    app.run(host='0.0.0.0', port=port, debug=debug_mode)

