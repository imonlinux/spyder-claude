# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""Encryption utilities for secure credential storage."""

import hashlib
import os
import platform
from base64 import urlsafe_b64encode
from cryptography.fernet import Fernet
from typing import Optional


class EncryptionManager:
    """Manages encryption/decryption using Fernet (AES-128-CBC)."""

    def __init__(self, custom_salt: Optional[str] = None):
        """Initialize encryption manager with system-specific key derivation.

        Args:
            custom_salt: Optional custom salt for testing purposes
        """
        self._key = self._derive_system_key(custom_salt)
        self._cipher = Fernet(self._key)

    def _derive_system_key(self, custom_salt: Optional[str] = None) -> bytes:
        """Derive encryption key from system-specific data.

        Combines machine identifier and user home directory to create a
        system-specific key that works across reinstall but not across machines.

        Args:
            custom_salt: Optional custom salt for testing

        Returns:
            32-byte encryption key suitable for Fernet
        """
        # Use custom salt if provided (for testing), otherwise derive from system
        if custom_salt:
            salt = custom_salt.encode()
        else:
            # System-specific: hostname + user home directory
            system_id = platform.node() + os.path.expanduser("~")
            salt = system_id.encode()

        # Derive 32-byte key using SHA-256
        return hashlib.sha256(salt).digest()

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext string.

        Args:
            plaintext: String to encrypt

        Returns:
            URL-safe base64 encoded ciphertext

        Raises:
            ValueError: If plaintext is not a string
        """
        if not isinstance(plaintext, str):
            raise ValueError("Plaintext must be a string")

        if not plaintext:
            return ""

        encrypted = self._cipher.encrypt(plaintext.encode('utf-8'))
        return encrypted.decode('utf-8')

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext string.

        Args:
            ciphertext: URL-safe base64 encoded ciphertext

        Returns:
            Decrypted plaintext string

        Raises:
            ValueError: If decryption fails or ciphertext is invalid
        """
        if not ciphertext:
            return ""

        try:
            decrypted = self._cipher.decrypt(ciphertext.encode('utf-8'))
            return decrypted.decode('utf-8')
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

    def generate_key(self) -> str:
        """Generate a new Fernet key (for testing/validation).

        Returns:
            URL-safe base64 encoded 32-byte key
        """
        return Fernet.generate_key().decode('utf-8')


def test_encryption():
    """Test encryption/decryption cycle."""
    manager = EncryptionManager()
    test_data = "test-api-key-sk-ant-1234567890abcdefghijklmnopqrstuvwxyz"

    # Test encryption
    encrypted = manager.encrypt(test_data)
    assert encrypted != test_data
    assert len(encrypted) > 0

    # Test decryption
    decrypted = manager.decrypt(encrypted)
    assert decrypted == test_data

    # Test empty string
    assert manager.encrypt("") == ""
    assert manager.decrypt("") == ""

    print("✅ Encryption tests passed")
    return True


if __name__ == "__main__":
    test_encryption()