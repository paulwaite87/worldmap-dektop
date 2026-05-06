#!/usr/bin/env python3
import os
import sys
import logging

# Internal library import
from worldmap.lib.config import WorldMapConfig

logger = logging.getLogger(__name__)


class Updater:
    def __init__(self, config: WorldMapConfig, section: str):
        self.config = config
        self.section = section.lower()
        self.settings = config.get_section(self.section)
        self.common = config.get_section("common")
        self.workdir = self.common.get("workdir", ".")
        self.output_path = ""
        self.enabled = self.settings.getboolean("enabled", False)

    def exit_if_disabled(self):
        if not self.enabled:
            logger.info(f"{self.section} task disabled; skipping.")
            sys.exit(0)

    def get_output_path(self):
        return str(os.path.join(
            self.common.get("workdir", "."),
            self.settings.get("outfile"))
        )

    def set_output_path(self):
        self.output_path = self.get_output_path()
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        with open(self.output_path, "w") as _:
            pass

    def remove_output_file(self):
        """Clears the output file of this updater if it exists"""
        output_path = self.get_output_path()
        if output_path and os.path.exists(output_path) and os.path.isfile(output_path):
            os.remove(output_path)
