from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json
import base64
from sqlalchemy import LargeBinary
from src.lib import crypto

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<User {self.name}>'


class Appointment(db.Model):
    __tablename__ = 'appointment'
    __table_args__ = (
        db.UniqueConstraint('appointment_date', 'service_type', name='uq_appointment_date_service'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    appointment_date = db.Column(db.DateTime, nullable=False)
    service_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='agendado')
    google_event_id = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('appointments', lazy=True))
    
    def __repr__(self):
        return f'<Appointment {self.id} - {self.appointment_date}>'


class OAuthCredential(db.Model):
    """Armazena credenciais OAuth do Google de forma segura no banco.

    Em vez de persistir token na sessão, armazenamos aqui e colocamos
    apenas o `oauth_credential_id` na sessão do usuário.
    """
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.String(200), nullable=True)
    # legacy token (plaintext) kept for migration; prefer token_encrypted/token_nonce
    token = db.Column(db.Text, nullable=True)
    refresh_token = db.Column(db.Text, nullable=True)
    token_uri = db.Column(db.String(200), nullable=True)
    scopes = db.Column(db.Text, nullable=True)  # JSON encoded list
    expires_at = db.Column(db.DateTime, nullable=True)
    # Encrypted token storage
    token_encrypted = db.Column(LargeBinary, nullable=True)
    token_nonce = db.Column(LargeBinary, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    user = db.relationship('User', backref=db.backref('oauth_credentials', lazy=True))

    def to_credentials_dict(self):
        # Decrypt token if encrypted, otherwise return legacy token
        token_val = None
        if self.token_encrypted and self.token_nonce:
            try:
                token_val = crypto.decrypt_token(self.token_nonce, self.token_encrypted)
            except Exception:
                token_val = None
        if not token_val and self.token:
            token_val = self.token

        return {
            "token": token_val,
            "refresh_token": self.refresh_token,
            "token_uri": self.token_uri,
            "client_id": self.client_id,
            "scopes": json.loads(self.scopes) if self.scopes else None
        }

    def set_encrypted_token(self, plaintext_token: str):
        """Encripta e armazena token; limpa campo legacy `token`."""
        try:
            nonce, ciphertext = crypto.encrypt_token(plaintext_token)
            self.token_encrypted = ciphertext
            self.token_nonce = nonce
            self.token = None
        except Exception:
            # Se não houver chave, fallback para salvar em texto (não ideal)
            self.token = plaintext_token

    def get_decrypted_token(self) -> str:
        if self.token_encrypted and self.token_nonce:
            return crypto.decrypt_token(self.token_nonce, self.token_encrypted)
        return self.token

    def __repr__(self):
        return f'<OAuthCredential {self.id} client_id={self.client_id}>'

