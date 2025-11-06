# Cross-Platform Compatibility Guide

QueueCTL is designed to work seamlessly across different operating systems and shells.

## Supported Platforms

| Platform | Shell Support | Status |
|----------|--------------|--------|
| Windows 10/11 | PowerShell, CMD | ✅ Fully Supported |
| Linux (Ubuntu, Debian, etc.) | bash, zsh | ✅ Fully Supported |
| macOS | bash, zsh | ✅ Fully Supported |

## Shell-Specific Usage

### PowerShell (Windows)

**Enqueue Jobs:**
```powershell
# PowerShell format (auto-fixed)
python queuectl.py enqueue '{id:job1,command:echo Hello,max_retries:3}'

# Standard JSON with escaped quotes
python queuectl.py enqueue "{\"id\":\"job1\",\"command\":\"echo Hello\",\"max_retries\":3}"
```

**Note**: PowerShell strips quotes from single-quoted strings, so the CLI automatically fixes this format.

### Bash/Zsh (Linux/macOS)

**Enqueue Jobs:**
```bash
# Standard JSON format
python queuectl.py enqueue '{"id":"job1","command":"echo Hello","max_retries":3}'

# With double quotes (escape internal quotes)
python queuectl.py enqueue "{\"id\":\"job1\",\"command\":\"echo Hello\",\"max_retries\":3}"
```

### CMD (Windows)

**Enqueue Jobs:**
```cmd
rem Standard JSON with escaped quotes
python queuectl.py enqueue "{\"id\":\"job1\",\"command\":\"echo Hello\",\"max_retries\":3}"

rem Or use interactive mode
python queuectl.py enqueue
```

## Platform-Specific Features

### Command Execution

Commands are executed using the platform's default shell:
- **Windows**: Uses `cmd.exe` (or PowerShell if available)
- **Unix/Linux/macOS**: Uses `/bin/sh` (typically bash)

**Example Commands:**
```bash
# Works on both platforms
echo "Hello World"

# Platform-specific
# Windows: dir, type, timeout
# Unix: ls, cat, sleep
```

### Signal Handling

- **Unix/Linux/macOS**: Uses `SIGTERM` and `SIGKILL` for graceful shutdown
- **Windows**: Uses `taskkill` command and `SIGINT` for process termination

### File Paths

All file paths use platform-agnostic Python functions:
- Database: `queuectl.db` (relative path)
- Config: `queuectl.config.json` (relative path)
- PID file: `queuectl.workers.pid` (relative path)

These work correctly on all platforms.

## Testing Cross-Platform Compatibility

Run the cross-platform test:

```bash
python test_cross_platform.py
```

This tests:
- ✅ JSON parsing in different shell formats
- ✅ Command execution on different platforms
- ✅ Signal handling availability

## Known Differences

### Command Syntax

Some commands differ between platforms:

| Unix/Linux/macOS | Windows | Notes |
|------------------|---------|-------|
| `sleep 2` | `timeout /t 2` | Different delay commands |
| `ls -la` | `dir` | Directory listing |
| `cat file.txt` | `type file.txt` | File viewing |
| `echo $VAR` | `echo %VAR%` | Environment variables |

**Recommendation**: Use platform-agnostic commands or test commands on your target platform.

### Process Management

- **Unix**: Uses `os.kill()` with signal numbers
- **Windows**: Uses `taskkill` command-line tool

The CLI automatically detects the platform and uses the appropriate method.

## Troubleshooting

### Windows Issues

1. **"taskkill not found"**: Ensure you're running on Windows with standard system tools
2. **PowerShell JSON errors**: Use the auto-fixed format `{id:value,command:value}` or interactive mode
3. **Signal errors**: These are handled automatically; if issues persist, use `worker stop` command

### Unix/Linux Issues

1. **Permission errors**: Ensure script has execute permissions: `chmod +x queuectl.py`
2. **Signal handling**: Ensure you're not running in a restricted environment

### General Issues

1. **Unicode errors**: The CLI uses ASCII-safe characters for cross-platform compatibility
2. **Path issues**: All paths are relative and work across platforms
3. **Shell differences**: Use interactive mode if JSON parsing fails: `python queuectl.py enqueue`

## Best Practices

1. **Use interactive mode** when unsure about shell quoting:
   ```bash
   python queuectl.py enqueue
   ```

2. **Test commands** on your target platform before using in production

3. **Use platform-agnostic commands** when possible:
   - Python scripts: `python script.py`
   - Generic commands: `echo`, `echo` (works on both)

4. **Check platform** before using platform-specific features:
   ```python
   import platform
   if platform.system() == 'Windows':
       # Windows-specific code
   else:
       # Unix-specific code
   ```

## Verification

To verify cross-platform compatibility on your system:

```bash
# Test JSON parsing
python test_cross_platform.py

# Test basic functionality
python queuectl.py enqueue '{id:test,command:echo hello,max_retries:1}'
python queuectl.py worker start
python queuectl.py status
python queuectl.py worker stop
```

All tests should pass on your platform.

