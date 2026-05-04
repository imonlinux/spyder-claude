# Implementation Plan: Session Persistence & Secure Token Storage

## Overview

This plan adds two critical features to spyder-claude:
1. **Session Persistence**: Maintain conversation continuity across IDE restarts
2. **Secure Storage**: Encrypt API keys and sensitive data instead of plaintext storage

## Current State Analysis

### Existing Architecture
- **Session Management**: In-memory only (`self._session_id = ""`)
- **API Key Storage**: Plaintext in Spyder config file (line 46-48 in preferences.py)
- **Conversation History**: Not persisted
- **Configuration**: Uses Spyder's configuration system (CONF_SECTION = "spyder_claude")

### Security Issues
- API keys stored in plaintext (documented warning in preferences.py)
- Session IDs lost on restart (no persistence)
- No secure credential storage mechanism

## Implementation Plan

### Phase 1: Secure Storage Foundation

#### 1.1 Platform-Specific Secure Storage

**Implementation**: Create `spyder_claude/secure_storage.py`

```python
# Platform-specific secure storage backends
class SecureStorage(ABC):
    @abstractmethod
    def store(self, key: str, value: str) -> bool: pass

    @abstractmethod
    def retrieve(self, key: str) -> Optional[str]: pass

    @abstractmethod
    def delete(self, key: str) -> bool: pass

# Platform implementations:
- Windows: tkinter.font.tkinter.encryptedfile or DPAPI
- macOS: Keychain Services via security command
- Linux: Secret Service API (GNOME Keyring/KWallet)
- Fallback: Encrypted file with system key derivation
```

**Key Features**:
- Automatic platform detection
- Graceful fallback to encrypted file storage
- Error handling for corrupted/locked storage
- Thread-safe operations

#### 1.2 Data Encryption Layer

**Implementation**: Add encryption utilities

```python
from cryptography.fernet import Fernet
import hashlib
import platform

class EncryptionManager:
    def __init__(self):
        # System-specific key derivation
        self.key = self._derive_system_key()
        self.cipher = Fernet(self.key)

    def _derive_system_key(self):
        # Use system-specific secrets + user-specific salt
        system_id = platform.node() + os.path.expanduser("~")
        return hashlib.sha256(system_id.encode()).digest()[:32]

    def encrypt(self, plaintext: str) -> str:
        return self.cipher.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self.cipher.decrypt(ciphertext.encode()).decode()
```

### Phase 2: Session Persistence

#### 2.1 Session Data Model

**Implementation**: Create `spyder_claude/session.py`

```python
@dataclass
class SessionData:
    session_id: str
    created_at: datetime
    last_used: datetime
    model: str
    mode: str  # "cli" or "api"
    metadata: Dict[str, Any]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SessionData":
        return cls(**data)
```

#### 2.2 Session Manager

**Implementation**: Add session management to main widget

```python
class SessionManager:
    def __init__(self, secure_storage: SecureStorage):
        self.storage = secure_storage
        self.current_session: Optional[SessionData] = None

    def save_session(self, session_data: SessionData) -> bool:
        """Store session data securely"""
        try:
            serialized = json.dumps(session_data.to_dict())
            encrypted = self.encryption_manager.encrypt(serialized)
            return self.storage.store("active_session", encrypted)
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False

    def load_session(self) -> Optional[SessionData]:
        """Retrieve and decrypt session data"""
        try:
            encrypted = self.storage.retrieve("active_session")
            if not encrypted:
                return None

            serialized = self.encryption_manager.decrypt(encrypted)
            data = json.loads(serialized)
            return SessionData.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            return None

    def clear_session(self) -> bool:
        """Remove stored session"""
        return self.storage.delete("active_session")

    def is_session_valid(self, session: SessionData) -> bool:
        """Check if session is still valid (not too old, etc.)"""
        age = datetime.now() - session.last_used
        return age < timedelta(days=7)  # Sessions expire after 7 days
```

#### 2.3 Integration with Main Widget

**Changes to `main_widget.py`**:

```python
class ClaudeMainWidget(PluginMainWidget):
    def setup(self) -> None:
        # ... existing setup ...

        # Initialize session manager
        self.secure_storage = create_secure_storage()
        self.session_manager = SessionManager(self.secure_storage)
        self.encryption_manager = EncryptionManager()

        # Restore previous session on startup
        self._restore_session()

    def _restore_session(self) -> None:
        """Restore previous session if available"""
        session = self.session_manager.load_session()
        if session and self.session_manager.is_session_valid(session):
            self._session_id = session.session_id
            self._append_text(
                _("\n[previous conversation restored]\n")
            )
        else:
            self._session_id = ""

    def _on_session_id(self, session_id: str) -> None:
        """Handle new session ID from Claude"""
        self._session_id = session_id

        # Save session data
        session_data = SessionData(
            session_id=session_id,
            created_at=datetime.now(),
            last_used=datetime.now(),
            model=self.get_conf("model", default="sonnet"),
            mode="cli" if self.get_conf("use_cli", default=True) else "api",
            metadata={}
        )
        self.session_manager.save_session(session_data)

    def _on_new_chat(self) -> None:
        """Start fresh conversation"""
        self._session_id = ""
        self._session_allowed_tools.clear()
        self._response_area.clear()

        # Clear persisted session
        self.session_manager.clear_session()
```

### Phase 3: API Key Security

#### 3.1 Secure API Key Storage

**Changes to `preferences.py`**:

```python
class ClaudeConfigPage(PluginConfigPage):
    def setup_page(self):
        # ... existing setup ...

        # Modify API key widget to use secure storage
        api_key_widget = self.create_lineedit(
            _("Anthropic API key"),
            "api_key",  # This will now be a placeholder
            tip=_(
                "Your Anthropic API key. "
                "Required when using API mode. "
                "Stored securely using system credential manager."
            ),
        )
        # Remove the plaintext warning
        # Add secure storage indicator
```

#### 3.2 API Key Migration

**Implementation**: Create migration script

```python
def migrate_api_keys_to_secure_storage():
    """Migrate existing plaintext API keys to secure storage"""
    config = SpyderConfig.get_instance()
    old_key = config.get("spyder_claude", "api_key", default="")

    if old_key and not old_key.startswith("SECURE:"):
        # Migrate to secure storage
        secure_storage = create_secure_storage()
        encryption = EncryptionManager()

        try:
            encrypted = encryption.encrypt(old_key)
            secure_storage.store("api_key", encrypted)

            # Update config with placeholder
            config.set("spyder_claude", "api_key", "SECURE:stored")
            logger.info("API key migrated to secure storage")
        except Exception as e:
            logger.error(f"Failed to migrate API key: {e}")
```

#### 3.3 API Key Retrieval

**Changes to worker classes**:

```python
class _ClaudeAPIWorker(QObject):
    def configure(self, prompt: str, api_key: str, ...):
        # Handle secure storage placeholder
        if api_key == "SECURE:stored":
            api_key = self._load_secure_api_key()

        self._api_key = api_key
        # ... rest of configuration ...

    def _load_secure_api_key(self) -> str:
        """Load and decrypt API key from secure storage"""
        try:
            secure_storage = create_secure_storage()
            encryption = EncryptionManager()

            encrypted = secure_storage.retrieve("api_key")
            if not encrypted:
                raise ValueError("No API key found in secure storage")

            return encryption.decrypt(encrypted)
        except Exception as e:
            logger.error(f"Failed to load API key: {e}")
            return ""
```

### Phase 4: Enhanced Preferences UI

#### 4.1 Security Status Indicator

**Add to preferences page**:

```python
def setup_page(self):
    # ... existing setup ...

    # Add security status group
    security_group = QGroupBox(_("Security Status"))

    self.security_status_label = QLabel()
    self._update_security_status()

    test_connection_btn = QPushButton(_("Test API Connection"))
    test_connection_btn.clicked.connect(self._test_api_connection)

    migrate_btn = QPushButton(_("Migrate to Secure Storage"))
    migrate_btn.clicked.connect(self._migrate_to_secure_storage)

    security_layout = QVBoxLayout()
    security_layout.addWidget(self.security_status_label)
    security_layout.addWidget(test_connection_btn)
    security_layout.addWidget(migrate_btn)
    security_group.setLayout(security_layout)

    main_layout.addWidget(security_group)

def _update_security_status(self):
    """Update security status indicator"""
    secure_storage = create_secure_storage()

    if secure_storage.is_available():
        status = _("✅ Secure storage available")
        if secure_storage.retrieve("api_key"):
            status += _(" — API key stored securely")
    else:
        status = _("⚠️ Using fallback encrypted file storage")

    self.security_status_label.setText(status)
```

#### 4.2 API Key Input Handling

```python
def _on_api_key_changed(self, new_key: str):
    """Handle API key input with secure storage"""
    if new_key and not new_key.startswith("SECURE:"):
        # Save to secure storage
        try:
            secure_storage = create_secure_storage()
            encryption = EncryptionManager()

            encrypted = encryption.encrypt(new_key)
            secure_storage.store("api_key", encrypted)

            # Update config with placeholder
            self.set_option("api_key", "SECURE:stored")

            # Clear the input field for security
            self.api_key_widget.textbox.clear()

            QMessageBox.information(
                self,
                _("API Key Stored"),
                _("API key stored securely in system credential manager.")
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                _("Storage Error"),
                _(f"Failed to store API key securely: {e}")
            )
```

### Phase 5: Testing & Validation

#### 5.1 Unit Tests

**Create `tests/test_secure_storage.py`**:

```python
def test_secure_storage_encryption():
    """Test encryption/decryption cycle"""
    manager = EncryptionManager()
    plaintext = "test-api-key-12345"

    encrypted = manager.encrypt(plaintext)
    decrypted = manager.decrypt(encrypted)

    assert decrypted == plaintext
    assert encrypted != plaintext

def test_session_persistence():
    """Test session save/load cycle"""
    storage = InMemorySecureStorage()  # Test double
    manager = SessionManager(storage)

    session = SessionData(
        session_id="test-session-123",
        created_at=datetime.now(),
        last_used=datetime.now(),
        model="sonnet",
        mode="cli",
        metadata={}
    )

    assert manager.save_session(session)
    loaded = manager.load_session()

    assert loaded.session_id == session.session_id
    assert loaded.model == session.model

def test_api_key_migration():
    """Test API key migration from plaintext"""
    # Test migration logic
    pass
```

#### 5.2 Integration Tests

**Create `tests/test_session_integration.py`**:

```python
def test_session_restoration_on_startup():
    """Test that sessions are restored on widget startup"""
    # Simulate IDE restart scenario
    pass

def test_cross_restart_session_continuity():
    """Test conversation continuity across restarts"""
    # Test multi-turn conversation with simulated restarts
    pass

def test_secure_api_key_storage():
    """Test API key secure storage and retrieval"""
    # Test end-to-end API key storage workflow
    pass
```

### Phase 6: Documentation & Migration

#### 6.1 User Documentation

**Add to README.md**:

```markdown
## Security Features

### Secure Credential Storage
- API keys stored using system credential managers (Windows DPAPI,
  macOS Keychain, Linux Secret Service)
- Automatic migration from existing plaintext storage
- Fallback to encrypted file storage if credential managers unavailable

### Session Persistence
- Conversations maintained across IDE restarts
- Sessions auto-expire after 7 days
- "New Chat" clears persisted session
- Cross-platform compatibility

### Migration Guide

#### First-Time Setup (New Installations)
API keys are automatically stored securely. No action needed.

#### Existing Installations
1. Update to version 0.3.0+
2. Open Tools → Preferences → Claude
3. Click "Migrate to Secure Storage" button
4. API keys will be moved from plaintext to secure storage
```

#### 6.2 Developer Documentation

**Create MIGRATION.md**:

```markdown
# Migration Guide for Developers

## Breaking Changes
- `get_conf("api_key")` now returns "SECURE:stored" placeholder
- Use `SecureStorage` class for credential operations
- Session management now requires explicit session cleanup

## API Changes

### Before (0.2.x)
```python
api_key = self.get_conf("api_key", default="")
```

### After (0.3.x)
```python
from spyder_claude.secure_storage import create_secure_storage
from spyder_claude.encryption import EncryptionManager

secure_storage = create_secure_storage()
encryption = EncryptionManager()

encrypted_key = secure_storage.retrieve("api_key")
api_key = encryption.decrypt(encrypted_key) if encrypted_key else ""
```

## Testing Changes
- Add secure storage mocks to existing tests
- Test session persistence across widget lifecycle
- Validate API key migration from old versions
```

## Implementation Timeline

### Phase 1: Foundation (Week 1-2)
- [ ] Create secure storage abstraction layer
- [ ] Implement platform-specific backends
- [ ] Add encryption utilities
- [ ] Write unit tests for encryption

### Phase 2: Session Persistence (Week 2-3)
- [ ] Implement session data model
- [ ] Create session manager
- [ ] Integrate with main widget
- [ ] Test session restoration

### Phase 3: API Key Security (Week 3-4)
- [ ] Modify preferences UI for secure storage
- [ ] Implement API key migration
- [ ] Update worker classes for secure retrieval
- [ ] Test API key storage/retrieval

### Phase 4: UI & UX (Week 4-5)
- [ ] Add security status indicators
- [ ] Implement migration wizard
- [ ] Update user documentation
- [ ] Create migration guide

### Phase 5: Testing (Week 5-6)
- [ ] Complete unit test coverage
- [ ] Integration tests for cross-platform scenarios
- [ ] Security audit and penetration testing
- [ ] Performance testing

### Phase 6: Release (Week 6-7)
- [ ] Beta release with migration feedback
- [ ] Bug fixes and refinements
- [ ] Final documentation updates
- [ ] Version 0.3.0 release

## Security Considerations

### Encryption Standards
- **Algorithm**: Fernet (symmetric encryption using AES-128-CBC)
- **Key Derivation**: System-specific + user-specific salt
- **Platform Integration**: Uses OS credential managers when available

### Threat Model
- **Protected Against**:
  - File system access to config files
  - Config file backups/uploads
  - Casual inspection of settings

- **Not Protected Against**:
  - Compromised system with memory access
  - Keylogger attacks
  - System-level malware

### Compliance
- Follows Anthropic's API key security guidelines
- Compatible with enterprise security policies
- No data sent to external services (local-only encryption)

## Backward Compatibility

### Migration Strategy
1. **Automatic Detection**: Detect plaintext API keys on startup
2. **User Prompt**: Offer one-click migration to secure storage
3. **Graceful Fallback**: Continue working if migration fails
4. **Rollback Support**: Can revert to plaintext if needed (not recommended)

### Version Compatibility
- **0.2.x → 0.3.0**: Automatic migration on first run
- **0.3.0 → Future**: Secure storage format remains stable
- **Downgrade**: Can downgrade to 0.2.x (sessions lost, keys re-encrypted)

## Performance Impact

### Encryption Overhead
- **API Key Operations**: <10ms per operation
- **Session Operations**: <50ms per save/load
- **Startup Impact**: +100-200ms for session restoration
- **Memory Impact**: +1-2MB for encryption libraries

### Optimization Strategies
- Lazy loading of encryption libraries
- Caching of decrypted values in memory
- Background migration for large datasets
- Async session operations

## Success Metrics

### Security Metrics
- ✅ Zero plaintext API keys in config files
- ✅ All sessions encrypted at rest
- ✅ Security audit passes

### User Experience Metrics
- ✅ <5% failure rate for secure storage operations
- ✅ <500ms perceived delay for session restoration
- ✅ 95% successful migration rate

### Functional Metrics
- ✅ 100% session restoration accuracy
- ✅ Zero data loss during migration
- ✅ Cross-platform parity

## Dependencies

### New Dependencies
```toml
[project.dependencies]
cryptography = ">=41.0.0"  # For encryption
keyring = ">=24.0.0"       # For platform credential managers (optional)
```

### Optional Dependencies
```toml
[project.optional-dependencies]
windows = ["pywin32>=306"]  # Windows DPAPI support
macos = ["pyobjc-framework-Security>=9.0"]  # macOS Keychain
linux = ["secretstorage>=3.3"]  # Linux Secret Service
```

## Risks & Mitigation

### Technical Risks
1. **Platform Compatibility**: Different credential managers behave differently
   - *Mitigation*: Comprehensive testing on all platforms

2. **Data Corruption**: Encrypted data could become corrupted
   - *Mitigation*: Validation, backups, rollback options

3. **Performance**: Encryption operations could slow down the UI
   - *Mitigation*: Async operations, caching, background tasks

### User Experience Risks
1. **Migration Failures**: Users could lose API keys during migration
   - *Mitigation*: Backup before migration, clear error messages

2. **Confusion**: Users might not understand the security changes
   - *Mitigation*: Clear documentation, in-app guidance

3. **Lockout**: Users could lose access to their credentials
   - *Mitigation*: Recovery options, manual key re-entry support

## Conclusion

This implementation plan provides a comprehensive approach to adding session persistence and secure token storage to spyder-claude while maintaining backward compatibility and ensuring cross-platform security. The phased approach allows for incremental development, testing, and validation at each stage.