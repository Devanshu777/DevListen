"""
Windows DPAPI and AES-256-GCM encryption envelope for DevListen.
Guarantees zero plaintext exposure on disk. All keys are derived from
the Windows User credential envelope (CryptProtectData).
"""
import os
import ctypes
from ctypes import wintypes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Windows DPAPI structures
class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte))
    ]

_crypt32 = ctypes.windll.crypt32
_kernel32 = ctypes.windll.kernel32

def dpapi_protect(plaintext_bytes: bytes) -> bytes:
    """Encrypts bytes using Windows DPAPI tied to current user account."""
    in_blob = DATA_BLOB(len(plaintext_bytes), ctypes.cast(ctypes.create_string_buffer(plaintext_bytes), ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()

    # CRYPTPROTECT_UI_FORBIDDEN = 0x1
    if not _crypt32.CryptProtectData(ctypes.byref(in_blob), "DevListen Master Key", None, None, None, 0x1, ctypes.byref(out_blob)):
        raise ctypes.WinError()

    try:
        encrypted_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return encrypted_bytes
    finally:
        _kernel32.LocalFree(out_blob.pbData)

def dpapi_unprotect(ciphertext_bytes: bytes) -> bytes:
    """Decrypts bytes using Windows DPAPI tied to current user account."""
    in_blob = DATA_BLOB(len(ciphertext_bytes), ctypes.cast(ctypes.create_string_buffer(ciphertext_bytes), ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()

    if not _crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0x1, ctypes.byref(out_blob)):
        raise ctypes.WinError()

    try:
        decrypted_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return decrypted_bytes
    finally:
        _kernel32.LocalFree(out_blob.pbData)

class VaultCrypto:
    """High-speed AES-256-GCM symmetric encryption using DPAPI-secured master key."""
    _master_key: bytes = None

    @classmethod
    def get_master_key(cls, key_path: str = "") -> bytes:
        if cls._master_key is not None:
            return cls._master_key

        if not key_path:
            appdata = os.getenv("LOCALAPPDATA", os.path.expanduser("~"))
            vault_dir = os.path.join(appdata, "DevListen")
            os.makedirs(vault_dir, exist_ok=True)
            key_path = os.path.join(vault_dir, "vault.key")

        if os.path.exists(key_path):
            with open(key_path, "rb") as f:
                encrypted_key = f.read()
            cls._master_key = dpapi_unprotect(encrypted_key)
        else:
            # Generate new 256-bit AES key
            new_key = AESGCM.generate_key(bit_length=256)
            encrypted_key = dpapi_protect(new_key)
            with open(key_path, "wb") as f:
                f.write(encrypted_key)
            cls._master_key = new_key

        return cls._master_key

    @classmethod
    def encrypt_data(cls, plaintext: str) -> bytes:
        """Encrypts string into AES-256-GCM ciphertext (nonce + ciphertext + tag)."""
        key = cls.get_master_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return nonce + ciphertext

    @classmethod
    def decrypt_data(cls, encrypted_blob: bytes) -> str:
        """Decrypts AES-256-GCM blob back into plaintext string."""
        key = cls.get_master_key()
        aesgcm = AESGCM(key)
        nonce = encrypted_blob[:12]
        ciphertext = encrypted_blob[12:]
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
