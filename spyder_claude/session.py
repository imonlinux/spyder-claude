# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""Session persistence for conversation continuity across IDE restarts."""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from .secure_storage import SecureStorage
from .encryption import EncryptionManager

logger = logging.getLogger(__name__)


@dataclass
class SessionData:
    """Data model for Claude conversation session."""

    session_id: str
    created_at: datetime
    last_used: datetime
    model: str
    mode: str  # "cli" or "api"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary."""
        data = asdict(self)
        # Convert datetime objects to ISO format strings
        data['created_at'] = self.created_at.isoformat()
        data['last_used'] = self.last_used.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "SessionData":
        """Create from JSON-serializable dictionary."""
        # Convert ISO format strings back to datetime objects
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'last_used' in data and isinstance(data['last_used'], str):
            data['last_used'] = datetime.fromisoformat(data['last_used'])
        return cls(**data)

    def is_expired(self, max_age_days: int = 7) -> bool:
        """Check if session has expired.

        Args:
            max_age_days: Maximum age in days before session expires

        Returns:
            True if session is expired, False otherwise
        """
        age = datetime.now() - self.last_used
        return age > timedelta(days=max_age_days)

    def update_last_used(self):
        """Update the last_used timestamp to current time."""
        self.last_used = datetime.now()


class SessionManager:
    """Manages Claude session persistence with secure storage."""

    # Session storage key
    SESSION_KEY = "active_session"
    DEFAULT_MAX_AGE_DAYS = 7

    def __init__(self, secure_storage: Optional[SecureStorage] = None):
        """Initialize session manager.

        Args:
            secure_storage: Secure storage instance (creates default if None)
        """
        if secure_storage is None:
            from .secure_storage import create_secure_storage
            secure_storage = create_secure_storage()

        self.storage = secure_storage
        self.encryption = EncryptionManager()
        self.current_session: Optional[SessionData] = None

    def save_session(self, session_data: SessionData) -> bool:
        """Store session data securely.

        Args:
            session_data: Session data to store

        Returns:
            True if successful, False otherwise
        """
        try:
            # Update last_used timestamp
            session_data.update_last_used()

            # Serialize to JSON
            serialized = json.dumps(session_data.to_dict())

            # Encrypt
            encrypted = self.encryption.encrypt(serialized)

            # Store securely
            success = self.storage.store(self.SESSION_KEY, encrypted)

            if success:
                self.current_session = session_data
                logger.info(f"Saved session: {session_data.session_id}")
            else:
                logger.error("Failed to save session to secure storage")

            return success
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False

    def load_session(self, max_age_days: Optional[int] = None) -> Optional[SessionData]:
        """Retrieve and decrypt session data.

        Args:
            max_age_days: Maximum age in days (uses default if None)

        Returns:
            Session data if found and valid, None otherwise
        """
        try:
            # Retrieve from storage
            encrypted = self.storage.retrieve(self.SESSION_KEY)
            if not encrypted:
                logger.debug("No existing session found")
                return None

            # Decrypt
            decrypted = self.encryption.decrypt(encrypted)

            # Deserialize from JSON
            data = json.loads(decrypted)
            session = SessionData.from_dict(data)

            # Check if session has expired
            max_age = max_age_days or self.DEFAULT_MAX_AGE_DAYS
            if session.is_expired(max_age):
                logger.info(f"Session expired (age > {max_age} days)")
                self.clear_session()
                return None

            self.current_session = session
            logger.info(f"Loaded session: {session.session_id}")
            return session

        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            # Clear corrupted session
            self.clear_session()
            return None

    def clear_session(self) -> bool:
        """Remove stored session data.

        Returns:
            True if successful, False otherwise
        """
        try:
            success = self.storage.delete(self.SESSION_KEY)
            if success:
                self.current_session = None
                logger.info("Cleared stored session")
            return success
        except Exception as e:
            logger.error(f"Failed to clear session: {e}")
            return False

    def get_session_id(self) -> Optional[str]:
        """Get current session ID.

        Returns:
            Session ID if session exists, None otherwise
        """
        if self.current_session:
            return self.current_session.session_id

        # Try loading from storage
        session = self.load_session()
        return session.session_id if session else None

    def is_session_valid(self, max_age_days: Optional[int] = None) -> bool:
        """Check if current session is valid.

        Args:
            max_age_days: Maximum age in days (uses default if None)

        Returns:
            True if session exists and is valid, False otherwise
        """
        if self.current_session:
            max_age = max_age_days or self.DEFAULT_MAX_AGE_DAYS
            return not self.current_session.is_expired(max_age)

        # Try loading from storage
        session = self.load_session(max_age_days)
        return session is not None

    def create_session(
        self,
        session_id: str,
        model: str,
        mode: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SessionData:
        """Create new session data.

        Args:
            session_id: Claude session ID
            model: Model name (e.g., "sonnet", "opus", "haiku")
            mode: Operation mode ("cli" or "api")
            metadata: Optional metadata dictionary

        Returns:
            New SessionData instance
        """
        now = datetime.now()
        session = SessionData(
            session_id=session_id,
            created_at=now,
            last_used=now,
            model=model,
            mode=mode,
            metadata=metadata or {}
        )

        # Save to storage
        self.save_session(session)
        return session


def test_session_manager():
    """Test session management functionality."""
    from .secure_storage import EncryptedFileStorage

    # Use in-memory storage for testing
    storage = EncryptedFileStorage()
    manager = SessionManager(storage)

    # Clean up any existing test data
    manager.clear_session()

    # Test session creation
    session_id = "test-session-123"
    model = "sonnet"
    mode = "cli"

    session = manager.create_session(session_id, model, mode)
    assert session.session_id == session_id
    assert session.model == model
    assert session.mode == mode

    # Test session retrieval
    loaded_session = manager.load_session()
    assert loaded_session is not None
    assert loaded_session.session_id == session_id
    assert loaded_session.model == model

    # Test session expiration (should not be expired)
    assert not loaded_session.is_expired()
    assert manager.is_session_valid()

    # Test session clearing
    assert manager.clear_session()
    assert manager.load_session() is None
    assert not manager.is_session_valid()

    print("✅ Session manager tests passed")
    return True


if __name__ == "__main__":
    test_session_manager()