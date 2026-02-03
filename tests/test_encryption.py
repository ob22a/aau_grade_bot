import pytest
import os
import base64
from services.credential_service import CredentialService

@pytest.fixture
def service():
    # Mock encryption key (32 bytes base64)
    key = os.urandom(32)
    os.environ["ENCRYPTION_KEY"] = base64.b64encode(key).decode()
    return CredentialService()

def test_encryption_decryption(service):
    password = "secret_password_123"
    encrypted, iv = service.encrypt_password(password)
    
    assert encrypted != password
    assert len(iv) > 0
    
    decrypted = service.decrypt_password(encrypted, iv)
    assert decrypted == password

def test_different_ivs(service):
    password = "same_password"
    enc1, iv1 = service.encrypt_password(password)
    enc2, iv2 = service.encrypt_password(password)
    
    assert iv1 != iv2
    assert enc1 != enc2  # Due to different IVs
