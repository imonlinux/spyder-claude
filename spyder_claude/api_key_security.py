# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""Secure API key storage and migration utilities."""

import logging
from typing import Optional

from .secure_storage import SecureStorage, create_secure_storage
from .encryption import EncryptionManager

logger = logging.getLogger(__name__)

# Constants for secure storage
API_KEY_STORAGE_KEY = "claude_api_key"
SECURE_PLACEHOLDER = "SECURE:stored"


class APIKeySecurity:
    """Manages secure API key storage and migration."""

    def __init__(self, secure_storage: Optional[SecureStorage] = None):
        """Initialize API key security manager.

        Args:
            secure_storage: Secure storage instance (creates default if None)
        """
        self.storage = secure_storage or create_secure_storage()
        self.encryption = EncryptionManager()

    def store_api_key(self, api_key: str) -> bool:
        """Store API key securely.

        Args:
            api_key: API key to store

        Returns:
            True if successful, False otherwise
        """
        try:
            if not api_key or api_key == SECURE_PLACEHOLDER:
                logger.warning("Invalid API key for storage")
                return False

            # Encrypt and store
            encrypted = self.encryption.encrypt(api_key)
            success = self.storage.store(API_KEY_STORAGE_KEY, encrypted)

            if success:
                logger.info("API key stored securely")
            else:
                logger.error("Failed to store API key")

            return success
        except Exception as e:
            logger.error(f"Failed to store API key: {e}")
            return False

    def retrieve_api_key(self) -> Optional[str]:
        """Retrieve and decrypt API key.

        Returns:
            Decrypted API key or None if not found
        """
        try:
            # Retrieve from storage
            encrypted = self.storage.retrieve(API_KEY_STORAGE_KEY)
            if not encrypted:
                logger.debug("No API key found in secure storage")
                return None

            # Decrypt
            decrypted = self.encryption.decrypt(encrypted)
            logger.info("API key retrieved from secure storage")
            return decrypted
        except Exception as e:
            logger.error(f"Failed to retrieve API key: {e}")
            return None

    def delete_api_key(self) -> bool:
        """Delete stored API key.

        Returns:
            True if successful, False otherwise
        """
        try:
            success = self.storage.delete(API_KEY_STORAGE_KEY)
            if success:
                logger.info("API key deleted from secure storage")
            return success
        except Exception as e:
            logger.error(f"Failed to delete API key: {e}")
            return False

    def has_api_key(self) -> bool:
        """Check if API key is stored.

        Returns:
            True if API key exists in storage, False otherwise
        """
        try:
            encrypted = self.storage.retrieve(API_KEY_STORAGE_KEY)
            return encrypted is not None
        except Exception:
            return False

    def is_secure_placeholder(self, value: str) -> bool:
        """Check if value is the secure storage placeholder.

        Args:
            value: Value to check

        Returns:
            True if value is the secure placeholder, False otherwise
        """
        return value == SECURE_PLACEHOLDER

    def migrate_from_plaintext(self, plaintext_key: str) -> bool:
        """Migrate plaintext API key to secure storage.

        Args:
            plaintext_key: API key in plaintext

        Returns:
            True if migration successful, False otherwise
        """
        try:
            if not plaintext_key or self.is_secure_placeholder(plaintext_key):
                logger.debug("No migration needed - already secure or empty")
                return True

            # Store securely
            success = self.store_api_key(plaintext_key)

            if success:
                # Clear plaintext from memory (best effort)
                plaintext_key = None
                logger.info("Successfully migrated API key to secure storage")

            return success
        except Exception as e:
            logger.error(f"Failed to migrate API key: {e}")
            return False

    def get_config_value(self) -> str:
        """Get value to store in Spyder config.

        Returns:
            SECURE_PLACEHOLDER if key is stored securely, empty string otherwise
        """
        return SECURE_PLACEHOLDER if self.has_api_key() else ""


def test_api_key_security():
    """Test API key security functionality."""
    from .secure_storage import EncryptedFileStorage

    # Use in-memory storage for testing
    storage = EncryptedFileStorage()
    security = APIKeySecurity(storage)

    # Clean up any existing test data
    security.delete_api_key()

    # Test API key storage
    test_key = "sk-ant-test1234567890abcdefghijklmnopqrstuvwxyz"
    assert security.store_api_key(test_key), "Failed to store API key"

    # Test API key retrieval
    retrieved = security.retrieve_api_key()
    assert retrieved == test_key, f"Retrieved key mismatch: {retrieved} != {test_key}"

    # Test has_api_key
    assert security.has_api_key(), "has_api_key returned False after storage"

    # Test secure placeholder
    assert security.is_secure_placeholder("SECURE:stored"), "is_secure_placeholder check failed"
    assert not security.is_secure_placeholder(test_key), "is_secure_placeholder false positive"

    # Test get_config_value
    config_value = security.get_config_value()
    assert config_value == SECURE_PLACEHOLDER, f"Config value mismatch: {config_value}"

    # Test migration
    security.delete_api_key()
    plaintext_key = "sk-ant-migrate-test-key"
    assert security.migrate_from_plaintext(plaintext_key), "Migration failed"
    assert security.has_api_key(), "API key not stored after migration"

    # Test deletion
    assert security.delete_api_key(), "Failed to delete API key"
    assert not security.has_api_key(), "API key still exists after deletion"

    print("✅ API key security tests passed")
    return True


if __name__ == "__main__":
    test_api_key_security()