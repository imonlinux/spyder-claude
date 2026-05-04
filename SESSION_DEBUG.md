# Session Persistence Debug Guide

## Quick Test

**1. Check if session files are created:**
```bash
# Check Flatpak cache
ls -la ~/.var/app/org.spyder_ide.spyder/cache/spyder-claude/

# Check regular cache
ls -la ~/.cache/spyder-claude/
```

**2. Enable debug logging:**
In Spyder, enable debug logging to see session management:
- Open Spyder
- Go to Tools → Preferences → Python Interpreter
- Check "Show internal console"
- Look for messages like `[spyder_claude]` when starting

**3. Expected behavior:**
- **On first query**: Should see `[spyder_claude] Saved session for persistence: <session_id>`
- **On restart**: Should see `[spyder_claude] Restored previous session: <session_id>`
- **In chat panel**: Should see `[previous conversation restored — session continued]`

## Current Issue

The fact that Claude doesn't remember the conversation context indicates:
1. Sessions are NOT being saved, OR
2. Sessions are NOT being restored, OR
3. The `--resume` parameter is NOT being used correctly

## Next Steps

1. **Check Spyder's internal console** for error messages
2. **Verify session files exist** in cache directories
3. **Test with a simple conversation** to see if sessions persist

## Temporary Workaround

Until we fix this issue, you'll need to:
- Re-establish context each time you restart Spyder
- Use "Send with current file" to include relevant context
- Or keep Spyder open for long conversations