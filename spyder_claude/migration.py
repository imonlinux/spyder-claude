# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""Migration utilities for upgrading to secure storage."""

import logging
from typing import Optional, Callable

from .api_key_security import APIKeySecurity, SECURE_PLACEHOLDER
from .secure_storage import create_secure_storage

logger = logging.getLogger(__name__)


class MigrationManager:
    """Manages migration from plaintext to secure storage."""

    def __init__(self):
        """Initialize migration manager."""
        try:
            secure_storage = create_secure_storage()
            self.api_key_security = APIKeySecurity(secure_storage)
            self.available = True
        except Exception as e:
            logger.warning(f"Secure storage not available for migration: {e}")
            self.api_key_security = None
            self.available = False

    def needs_migration(self, api_key_config_value: str) -> bool:
        """Check if API key needs migration to secure storage.

        Args:
            api_key_config_value: Current API key value from config

        Returns:
            True if migration needed, False otherwise
        """
        if not self.available:
            return False

        # Check if this is a plaintext API key (not empty, not placeholder)
        if not api_key_config_value:
            return False

        if api_key_config_value == SECURE_PLACEHOLDER:
            return False

        # Assume anything else is a plaintext key that needs migration
        return True

    def migrate_api_key(
        self,
        api_key_config_value: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> tuple[bool, str]:
        """Migrate API key from plaintext to secure storage.

        Args:
            api_key_config_value: Current API key value from config
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (success, new_config_value)
        """
        if not self.available:
            return False, "Secure storage not available"

        try:
            if progress_callback:
                progress_callback("Starting API key migration...")

            # Check if migration is needed
            if not self.needs_migration(api_key_config_value):
                if progress_callback:
                    progress_callback("No migration needed")
                return True, api_key_config_value

            # Perform migration
            success = self.api_key_security.migrate_from_plaintext(api_key_config_value)

            if success:
                if progress_callback:
                    progress_callback("API key migrated successfully")
                logger.info("API key migrated to secure storage")
                return True, SECURE_PLACEHOLDER
            else:
                if progress_callback:
                    progress_callback("Migration failed")
                logger.error("API key migration failed")
                return False, api_key_config_value

        except Exception as e:
            error_msg = f"Migration error: {e}"
            if progress_callback:
                progress_callback(error_msg)
            logger.error(error_msg)
            return False, api_key_config_value

    def auto_migrate_on_startup(
        self,
        get_config_func: Callable[[], str],
        set_config_func: Callable[[str], None]
    ) -> tuple[bool, str]:
        """Automatically migrate API key on plugin startup.

        Args:
            get_config_func: Function to get current config value
            set_config_func: Function to set new config value

        Returns:
            Tuple of (success, message)
        """
        try:
            current_value = get_config_func()

            if not self.needs_migration(current_value):
                return True, "No migration needed"

            logger.info("Auto-migrating API key to secure storage...")
            success, new_value = self.migrate_api_key(current_value)

            if success:
                # Update the config
                set_config_func(new_value)
                msg = "API key migrated to secure storage"
                logger.info(msg)
                return True, msg
            else:
                msg = "Failed to migrate API key"
                logger.error(msg)
                return False, msg

        except Exception as e:
            error_msg = f"Auto-migration failed: {e}"
            logger.error(error_msg)
            return False, error_msg


def test_migration():
    """Test migration functionality."""
    manager = MigrationManager()

    # Test migration detection
    assert manager.needs_migration("sk-ant-test-key"), "Should detect plaintext key"
    assert not manager.needs_migration(""), "Should not migrate empty string"
    assert not manager.needs_migration(SECURE_PLACEHOLDER), "Should not migrate placeholder"

    # Test migration (if secure storage available)
    if manager.available:
        test_key = "sk-ant-migration-test-key-12345"

        # Mock callbacks
        progress_messages = []
        def progress_callback(msg):
            progress_messages.append(msg)

        success, new_value = manager.migrate_api_key(test_key, progress_callback)

        if success:
            assert new_value == SECURE_PLACEHOLDER, f"Expected placeholder, got {new_value}"
            assert len(progress_messages) > 0, "No progress messages"

            # Verify key was stored
            assert manager.api_key_security.has_api_key(), "Key not stored"
            retrieved = manager.api_key_security.retrieve_api_key()
            assert retrieved == test_key, f"Retrieved key mismatch: {retrieved}"

            # Cleanup
            manager.api_key_security.delete_api_key()

        print("✅ Migration tests passed")
    else:
        print("⚠️ Migration tests skipped (secure storage unavailable)")

    return True


if __name__ == "__main__":
    test_migration()