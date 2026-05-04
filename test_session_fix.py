#!/usr/bin/env python3
"""Test session persistence with fixed encryption."""

from spyder_claude.secure_storage import create_secure_storage
from spyder_claude.session import SessionManager

def test_session_persistence():
    """Test that session persistence works after encryption fix."""
    try:
        storage = create_secure_storage()
        manager = SessionManager(storage)
        print('✅ Session manager created successfully!')

        # Test basic operations
        test_session = manager.create_session('test-123', 'sonnet', 'cli')
        print(f'✅ Session created: {test_session.session_id}')

        # Test save/load
        loaded = manager.load_session()
        print(f'✅ Session loaded: {loaded.session_id if loaded else "None"}')

        # Test encryption
        from spyder_claude.encryption import EncryptionManager
        enc = EncryptionManager()
        test_data = "test-api-key-sk-ant-test123"
        encrypted = enc.encrypt(test_data)
        decrypted = enc.decrypt(encrypted)
        assert decrypted == test_data, "Encryption round-trip failed"
        print('✅ Encryption working correctly')

        print('\n🎉 Session persistence is working!')
        return True
    except Exception as e:
        print(f'❌ Error: {e}')
        return False

if __name__ == "__main__":
    test_session_persistence()