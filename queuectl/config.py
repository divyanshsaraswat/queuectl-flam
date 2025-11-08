"""Configuration management module"""

import json
import os
from typing import Any, Optional
from filelock import FileLock


class Config:
    """Manages application configuration"""
    
    def __init__(self, config_path: str = "queuectl.config.json"):
        self.config_path = config_path
        self.lock_path = f"{config_path}.lock"
        self.lock = FileLock(self.lock_path, timeout=10)
        self.defaults = {
            "max_retries": 3,
            "backoff_base": 2,
            "default_timeout": 300  # 5 minutes default timeout
        }
        self._ensure_config_exists()
    
    def _ensure_config_exists(self):
        """Create config file with defaults if it doesn't exist"""
        if not os.path.exists(self.config_path):
            with self.lock:
                with open(self.config_path, 'w') as f:
                    json.dump(self.defaults, f, indent=2)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value"""
        with self.lock:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    return config.get(key, self.defaults.get(key, default))
            return self.defaults.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set a configuration value"""
        with self.lock:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
            else:
                config = self.defaults.copy()
            
            config[key] = value
            
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
    
    def get_all(self) -> dict:
        """Get all configuration values"""
        with self.lock:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    # Merge with defaults
                    result = self.defaults.copy()
                    result.update(config)
                    return result
            return self.defaults.copy()

