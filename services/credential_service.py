import os
import base64
import json
from typing import Optional, Tuple, Dict, Any
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from dotenv import load_dotenv

load_dotenv()

class EncryptionService:
    def __init__(self):
        # The key should be 32 bytes for AES-256
        key_str = os.getenv("ENCRYPTION_KEY")
        if not key_str:
            raise ValueError("ENCRYPTION_KEY not found in environment")
        self.key = base64.b64decode(key_str)

    def encrypt_string(self, text: str) -> Tuple[str, str]:
        """
        Returns (encrypted_base64, iv_base64)
        """
        if not text:
            return "", ""
            
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        
        # Pad data to 16 bytes
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(text.encode()) + padder.finalize()
        
        encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
        
        return base64.b64encode(encrypted_data).decode(), base64.b64encode(iv).decode()

    def decrypt_string(self, encrypted_b64: str, iv_b64: str) -> str:
        if not encrypted_b64 or not iv_b64:
            return ""
            
        iv = base64.b64decode(iv_b64)
        encrypted_data = base64.b64decode(encrypted_b64)
        
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        
        decrypted_padded_data = decryptor.update(encrypted_data) + decryptor.finalize()
        
        # Unpad
        unpadder = padding.PKCS7(128).unpadder()
        decrypted_data = unpadder.update(decrypted_padded_data) + unpadder.finalize()
        
        return decrypted_data.decode()

    def encrypt_json(self, data: Dict[str, Any]) -> Tuple[str, str]:
        json_str = json.dumps(data)
        return self.encrypt_string(json_str)

    def decrypt_json(self, encrypted_b64: str, iv_b64: str) -> Dict[str, Any]:
        json_str = self.decrypt_string(encrypted_b64, iv_b64)
        return json.loads(json_str) if json_str else {}

    # Alias for backward compatibility if needed, but we'll update callers
    def encrypt_password(self, password: str) -> Tuple[str, str]:
        return self.encrypt_string(password)

    def decrypt_password(self, encrypted_password_b64: str, iv_b64: str) -> str:
        return self.decrypt_string(encrypted_password_b64, iv_b64)
