import os
import configparser
import logging

from worldmap.lib.logging import set_loglevel

logger = logging.getLogger(__name__)

class WorldMapConfig:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        # Track the modification time to detect external changes
        self._last_mtime = self._get_current_mtime()
        self.has_changed = False
        self.load()

    def _get_current_mtime(self):
        """Returns the current modification time of the config file."""
        try:
            return os.path.getmtime(self.config_path)
        except OSError:
            return 0

    def check_if_changed(self) -> bool:
        """
        Returns True if the config file has been modified since the last check.
        Updates the internal timestamp reference, and stores the result.
        """
        current_mtime = self._get_current_mtime()
        if current_mtime > self._last_mtime:
            self._last_mtime = current_mtime
            return True
        return False

    def load(self):
        """Reads or re-reads the config file from disk."""
        if not os.path.exists(self.config_path):
            logger.error(f"Config file not found: {self.config_path}")
            return
        self.config.clear()
        self.config.read(self.config_path)
        self._inject_secrets()
        self.has_changed = self.check_if_changed()
        # Adjust log level for common (overall) logging
        log_level = self.get_setting("common", "log_level", None)
        if log_level:
            set_loglevel(log_level)

    def _inject_secrets(self):
        """Silently injects API keys from environment into the config object."""

        # Sections requiring an API key
        api_keys = {
            "shipping_collector": os.getenv("AIS_API_KEY"),
            "weather_scanner": os.getenv("OPENWEATHER_API_KEY"),
        }

        for section, api_key in api_keys.items():
            if self.config.has_section(section):
                if api_key:
                    self.config[section]["api_key"] = api_key

    def get_section(self, section):
        if self.config.has_section(section):
            return self.config[section]
        return self.config['DEFAULT']

    def section_enabled(self, section):
        if self.config.has_section(section):
            return self.config.getboolean(section, "enabled", fallback=False)
        return False

    def get_section_outfile(self, section):
        if self.config.has_section(section):
            return self.config.get(section, "outfile", fallback=None)
        return None

    def get_setting(self, section, setting, default=None):
        if self.config.has_section(section):
            return self.config.get(section, setting, fallback=default)
        return default
