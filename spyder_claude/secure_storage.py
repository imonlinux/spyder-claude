# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""Platform-specific secure credential storage."""

import abc
import json
import logging
import os
import platform
import tempfile
from pathlib import Path
from typing import Optional

from .encryption import EncryptionManager

logger = logging.getLogger(__name__)


class SecureStorage(abc.ABC):
    """Abstract base class for secure storage implementations."""

    @abc.abstractmethod
    def store(self, key: str, value: str) -> bool:
        """Store a key-value pair securely.

        Args:
            key: Storage key
            value: Value to store (will be encrypted)

        Returns:
            True if successful, False otherwise
        """
        pass

    @abc.abstractmethod
    def retrieve(self, key: str) -> Optional[str]:
        """Retrieve a value by key.

        Args:
            key: Storage key

        Returns:
            Decrypted value or None if not found
        """
        pass

    @abc.abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a key-value pair.

        Args:
            key: Storage key

        Returns:
            True if successful, False otherwise
        """
        pass

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if storage backend is available.

        Returns:
            True if available, False otherwise
        """
        pass


class EncryptedFileStorage(SecureStorage):
    """Fallback encrypted file storage using system-specific key derivation.

    Used when platform credential managers are unavailable.
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize encrypted file storage.

        Args:
            storage_dir: Directory for encrypted files (default: ~/.cache/spyder-claude/)
        """
        if storage_dir is None:
            cache_root = Path(
                os.environ.get("XDG_CACHE_HOME")
                or (Path.home() / ".cache")
            )
            storage_dir = cache_root / "spyder-claude"

        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.encryption = EncryptionManager()
        self._key_suffix = ".enc"

    def _get_file_path(self, key: str) -> Path:
        """Get file path for a given key."""
        # Sanitize key to be filesystem-safe
        safe_key = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in key)
        return self.storage_dir / f"{safe_key}{self._key_suffix}"

    def store(self, key: str, value: str) -> bool:
        """Store encrypted value in file."""
        try:
            encrypted = self.encryption.encrypt(value)
            file_path = self._get_file_path(key)

            # Write to temporary file first, then rename (atomic operation)
            fd, temp_path = tempfile.mkstemp(dir=self.storage_dir)
            try:
                with os.fdopen(fd, 'w') as f:
                    f.write(encrypted)

                # Atomic rename
                os.replace(temp_path, file_path)
                logger.debug(f"Stored encrypted key: {key}")
                return True
            except Exception:
                # Clean up temp file if something goes wrong
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.error(f"Failed to store key '{key}': {e}")
            return False

    def retrieve(self, key: str) -> Optional[str]:
        """Retrieve and decrypt value from file."""
        try:
            file_path = self._get_file_path(key)
            if not file_path.exists():
                return None

            with open(file_path, 'r') as f:
                encrypted = f.read()

            decrypted = self.encryption.decrypt(encrypted)
            logger.debug(f"Retrieved encrypted key: {key}")
            return decrypted
        except Exception as e:
            logger.error(f"Failed to retrieve key '{key}': {e}")
            return None

    def delete(self, key: str) -> bool:
        """Delete encrypted file."""
        try:
            file_path = self._get_file_path(key)
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"Deleted encrypted key: {key}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete key '{key}': {e}")
            return False

    def is_available(self) -> bool:
        """Check if storage directory is writable."""
        try:
            test_file = self.storage_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
            return True
        except Exception:
            return False


class WindowsSecureStorage(SecureStorage):
    """Windows DPAPI secure storage (requires pywin32)."""

    def __init__(self):
        """Initialize Windows secure storage."""
        try:
            import win32crypt
            import win32con
            self._win32crypt = win32crypt
            self._win32con = win32con
            self._available = True
        except ImportError:
            logger.warning("pywin32 not available, falling back to encrypted file storage")
            self._available = False
            self._fallback = EncryptedFileStorage()

    def store(self, key: str, value: str) -> bool:
        """Store value using Windows DPAPI."""
        if not self._available:
            return self._fallback.store(key, value)

        try:
            # Convert to bytes
            value_bytes = value.encode('utf-8')

            # Encrypt using DPAPI
            encrypted = self._win32crypt.CryptProtectData(
                value_bytes,
                f"spyder-claude:{key}",
                None,
                None,
                None,
                0
            )

            # Store in registry or file
            storage_dir = Path(os.environ.get('APPDATA', '~')) / "spyder-claude"
            storage_dir.mkdir(parents=True, exist_ok=True)
            key_file = storage_dir / f"{key}.dpapi"

            with open(key_file, 'wb') as f:
                f.write(encrypted)

            return True
        except Exception as e:
            logger.error(f"Windows secure storage failed: {e}")
            return False

    def retrieve(self, key: str) -> Optional[str]:
        """Retrieve value using Windows DPAPI."""
        if not self._available:
            return self._fallback.retrieve(key)

        try:
            storage_dir = Path(os.environ.get('APPDATA', '~')) / "spyder-claude"
            key_file = storage_dir / f"{key}.dpapi"

            if not key_file.exists():
                return None

            with open(key_file, 'rb') as f:
                encrypted = f.read()

            # Decrypt using DPAPI
            decrypted = self._win32crypt.CryptUnprotectData(
                encrypted,
                None,
                None,
                None,
                0
            )

            return decrypted[0].decode('utf-8')
        except Exception as e:
            logger.error(f"Windows secure storage retrieval failed: {e}")
            return None

    def delete(self, key: str) -> bool:
        """Delete value from Windows secure storage."""
        if not self._available:
            return self._fallback.delete(key)

        try:
            storage_dir = Path(os.environ.get('APPDATA', '~')) / "spyder-claude"
            key_file = storage_dir / f"{key}.dpapi"

            if key_file.exists():
                key_file.unlink()
                return True
            return False
        except Exception as e:
            logger.error(f"Windows secure storage deletion failed: {e}")
            return False

    def is_available(self) -> bool:
        """Check if Windows DPAPI is available."""
        return self._available


class MacOSSecureStorage(SecureStorage):
    """macOS Keychain secure storage."""

    def __init__(self):
        """Initialize macOS secure storage."""
        self.system = platform.system()
        if self.system != "Darwin":
            self._available = False
            self._fallback = EncryptedFileStorage()
            return

        # Check if security command is available
        try:
            import subprocess
            result = subprocess.run(['security', '-h'],
                                  capture_output=True,
                                  timeout=5)
            self._available = result.returncode == 0
        except Exception:
            logger.warning("macOS keychain not available, falling back to encrypted file storage")
            self._available = False
            self._fallback = EncryptedFileStorage()

    def store(self, key: str, value: str) -> bool:
        """Store value in macOS Keychain."""
        if not self._available:
            return self._fallback.store(key, value)

        try:
            import subprocess
            # Use generic password for internet accounts
            account = f"spyder-claude-{key}"
            service = "spyder-claude"

            # Delete existing entry first
            subprocess.run([
                'security', 'delete-generic-password',
                '-a', account,
                '-s', service
            ], capture_output=True)

            # Add new password
            result = subprocess.run([
                'security', 'add-generic-password',
                '-a', account,
                '-s', service,
                '-w', value,
                '-U'  # Update existing
            ], capture_output=True, input=value.encode())

            return result.returncode == 0
        except Exception as e:
            logger.error(f"macOS keychain storage failed: {e}")
            return False

    def retrieve(self, key: str) -> Optional[str]:
        """Retrieve value from macOS Keychain."""
        if not self._available:
            return self._fallback.retrieve(key)

        try:
            import subprocess
            account = f"spyder-claude-{key}"
            service = "spyder-claude"

            result = subprocess.run([
                'security', 'find-generic-password',
                '-a', account,
                '-s', service,
                '-w'  # Output password only
            ], capture_output=True, text=True)

            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as e:
            logger.error(f"macOS keychain retrieval failed: {e}")
            return None

    def delete(self, key: str) -> bool:
        """Delete value from macOS Keychain."""
        if not self._available:
            return self._fallback.delete(key)

        try:
            import subprocess
            account = f"spyder-claude-{key}"
            service = "spyder-claude"

            result = subprocess.run([
                'security', 'delete-generic-password',
                '-a', account,
                '-s', service
            ], capture_output=True)

            return result.returncode == 0
        except Exception as e:
            logger.error(f"macOS keychain deletion failed: {e}")
            return False

    def is_available(self) -> bool:
        """Check if macOS keychain is available."""
        return self._available


def create_secure_storage() -> SecureStorage:
    """Create appropriate secure storage implementation for current platform.

    Returns:
        Platform-specific secure storage instance with fallback
    """
    system = platform.system()

    # Try platform-specific implementations
    if system == "Windows":
        storage = WindowsSecureStorage()
        if storage.is_available():
            logger.info("Using Windows DPAPI secure storage")
            return storage
    elif system == "Darwin":
        storage = MacOSSecureStorage()
        if storage.is_available():
            logger.info("Using macOS Keychain secure storage")
            return storage

    # Fallback to encrypted file storage
    logger.info(f"Using encrypted file storage for {system}")
    return EncryptedFileStorage()


def test_secure_storage():
    """Test secure storage implementation."""
    storage = create_secure_storage()

    # Test availability
    assert storage.is_available(), "Secure storage not available"

    # Test store/retrieve cycle
    test_key = "test_api_key"
    test_value = "sk-ant-test123456789"

    # Clean up any existing test data
    storage.delete(test_key)

    # Store
    assert storage.store(test_key, test_value), "Failed to store value"

    # Retrieve
    retrieved = storage.retrieve(test_key)
    assert retrieved == test_value, f"Retrieved value mismatch: {retrieved} != {test_value}"

    # Delete
    assert storage.delete(test_key), "Failed to delete value"

    # Verify deletion
    assert storage.retrieve(test_key) is None, "Value still exists after deletion"

    print("✅ Secure storage tests passed")
    return True


if __name__ == "__main__":
    test_secure_storage()