import os
import base64
import logging
from typing import Tuple, Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:  # pragma: no cover - runtime import warning
    AESGCM = None

logger = logging.getLogger(__name__)


def _get_key() -> Optional[bytes]:
    """Lê a chave de criptografia da env var `TOKEN_ENCRYPTION_KEY`.

    Espera-se uma string base64 urlsafe representando 32 bytes (AES-256).
    Retorna None se não configurada.
    """
    val = os.environ.get('TOKEN_ENCRYPTION_KEY')
    if not val:
        return None
    try:
        key = base64.urlsafe_b64decode(val)
        if len(key) not in (16, 24, 32):
            logger.error('TOKEN_ENCRYPTION_KEY tem tamanho inválido (esperado 16/24/32 bytes)')
            return None
        return key
    except Exception as e:
        logger.exception('Falha ao decodificar TOKEN_ENCRYPTION_KEY: %s', e)
        return None


def encrypt_token(plaintext: str) -> Tuple[bytes, bytes]:
    """Encripta `plaintext` retornando (nonce, ciphertext).

    Usa AESGCM com chave de `TOKEN_ENCRYPTION_KEY`.
    Levanta RuntimeError se AESGCM não estiver disponível ou chave ausente.
    """
    key = _get_key()
    if AESGCM is None:
        raise RuntimeError('cryptography library não encontrada')
    if key is None:
        raise RuntimeError('TOKEN_ENCRYPTION_KEY não configurada')

    aesgcm = AESGCM(key)
    # AESGCM nonce recomendado 12 bytes
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
    return nonce, ciphertext


def decrypt_token(nonce: bytes, ciphertext: bytes) -> str:
    """Desencripta e retorna string plaintext.

    Levanta RuntimeError se desencriptação falhar ou chave ausente.
    """
    key = _get_key()
    if AESGCM is None:
        raise RuntimeError('cryptography library não encontrada')
    if key is None:
        raise RuntimeError('TOKEN_ENCRYPTION_KEY não configurada')

    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode('utf-8')
