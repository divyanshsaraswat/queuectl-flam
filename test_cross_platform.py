#!/usr/bin/env python3
"""Test cross-platform compatibility"""

import sys
import platform
import subprocess
import json

def test_json_parsing():
    """Test JSON parsing with different shell formats"""
    print("\n" + "="*60)
    print("Testing JSON Parsing (Cross-Shell Compatibility)")
    print("="*60)
    
    from queuectl.cli import enqueue
    from queuectl.storage import JobStorage
    
    # Test different formats
    test_cases = [
        # (format_name, json_string)
        ("Standard JSON", '{"id":"test1","command":"echo hello","max_retries":3}'),
        ("PowerShell format", '{id:test2,command:echo hello,max_retries:3}'),
        ("PowerShell with spaces", '{id:test3,command:echo hello world,max_retries:2}'),
    ]
    
    storage = JobStorage("test_platform.db")
    
    for format_name, json_str in test_cases:
        try:
            # Parse JSON
            if '{' in json_str and '}' in json_str and '"' not in json_str:
                # PowerShell format - use the fix logic
                import re
                def fix_json_match(m):
                    key = m.group(1)
                    value = m.group(2).strip()
                    if value.isdigit() or (value.replace('.', '', 1).isdigit() and value.count('.') == 1):
                        return f'"{key}":{value}'
                    else:
                        return f'"{key}":"{value}"'
                json_str = re.sub(r'(\w+):([^,}]+)', fix_json_match, json_str)
            
            job_dict = json.loads(json_str)
            print(f"[OK] {format_name}: Successfully parsed")
            print(f"  Job ID: {job_dict.get('id')}, Command: {job_dict.get('command')}")
        except Exception as e:
            print(f"[FAIL] {format_name}: Failed - {e}")
    
    # Cleanup
    import os
    if os.path.exists("test_platform.db"):
        os.remove("test_platform.db")
    if os.path.exists("test_platform.db.lock"):
        os.remove("test_platform.db.lock")


def test_command_execution():
    """Test command execution across platforms"""
    print("\n" + "="*60)
    print("Testing Command Execution (Cross-Platform)")
    print("="*60)
    
    from queuectl.worker import Worker
    from queuectl.storage import JobStorage
    from queuectl.config import Config
    
    storage = JobStorage("test_platform.db")
    config = Config()
    
    worker = Worker(1, storage, config)
    
    # Test platform-specific commands
    if platform.system() == 'Windows':
        test_commands = [
            ("Windows echo", "echo Hello Windows"),
            ("Windows dir", "dir /b"),
        ]
    else:
        test_commands = [
            ("Unix echo", "echo Hello Unix"),
            ("Unix ls", "ls -la"),
        ]
    
    for cmd_name, command in test_commands:
        success, error = worker._execute_command(command)
        if success:
            print(f"[OK] {cmd_name}: Command executed successfully")
        else:
            print(f"[FAIL] {cmd_name}: Failed - {error}")
    
    # Cleanup
    import os
    if os.path.exists("test_platform.db"):
        os.remove("test_platform.db")
    if os.path.exists("test_platform.db.lock"):
        os.remove("test_platform.db.lock")


def test_signal_handling():
    """Test signal handling availability"""
    print("\n" + "="*60)
    print("Testing Signal Handling (Cross-Platform)")
    print("="*60)
    
    import signal
    
    print(f"Platform: {platform.system()}")
    print(f"SIGINT available: {hasattr(signal, 'SIGINT')}")
    print(f"SIGTERM available: {hasattr(signal, 'SIGTERM')}")
    print(f"SIGKILL available: {hasattr(signal, 'SIGKILL')}")
    
    if platform.system() == 'Windows':
        print(f"SIGBREAK available: {hasattr(signal, 'SIGBREAK')}")
        if hasattr(signal, 'CTRL_C_EVENT'):
            print(f"CTRL_C_EVENT available: True")
        if hasattr(signal, 'CTRL_BREAK_EVENT'):
            print(f"CTRL_BREAK_EVENT available: True")


def main():
    print("\n" + "="*60)
    print("QueueCTL Cross-Platform Compatibility Test")
    print("="*60)
    print(f"Python Version: {sys.version}")
    print(f"Platform: {platform.system()} {platform.release()}")
    
    test_json_parsing()
    test_command_execution()
    test_signal_handling()
    
    print("\n" + "="*60)
    print("Cross-Platform Test Complete")
    print("="*60)


if __name__ == "__main__":
    main()

