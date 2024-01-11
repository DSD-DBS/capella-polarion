# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Tool for CLI work."""
from __future__ import annotations

import json
import logging
import pathlib
import typing

import capellambse
import click

from capella2polarion.connectors import polarion_worker as pw
from capella2polarion.converters import converter_config

logger = logging.getLogger(__name__)


class Capella2PolarionCli:
    """Call Level Interface."""

    def __init__(
        self,
        debug: bool,
        polarion_project_id: str,
        polarion_url: str,
        polarion_pat: str,
        polarion_delete_work_items: bool,
        capella_diagram_cache_folder_path: pathlib.Path | None,
        capella_model: capellambse.MelodyModel,
        synchronize_config_io: typing.TextIO,
    ) -> None:
        self.debug = debug
        self.polarion_params = pw.PolarionWorkerParams(
            polarion_project_id,
            polarion_url,
            polarion_pat,
            polarion_delete_work_items,
        )
        if capella_diagram_cache_folder_path is None:
            raise ValueError("CapellaDiagramCacheFolderPath not filled")

        self.capella_diagram_cache_folder_path = (
            capella_diagram_cache_folder_path
        )
        self.capella_diagram_cache_index_file_path = (
            self.capella_diagram_cache_folder_path / "index.json"
        )
        self.capella_diagram_cache_index_content: list[
            dict[str, typing.Any]
        ] = []
        self.capella_model: capellambse.MelodyModel = capella_model
        self.synchronize_config_io: typing.TextIO = synchronize_config_io
        self.synchronize_config_content: dict[str, typing.Any] = {}
        self.synchronize_config_roles: dict[str, list[str]] | None = None
        self.echo = click.echo
        self.config = converter_config.ConverterConfig()

    def _none_save_value_string(self, value: str | None) -> str | None:
        return "None" if value is None else value

    def print_state(self) -> None:
        """Print the State of the cli tool."""

        def _type(value):
            return f"type: {type(value)}"

        def _value(value):
            return value

        self.echo("---------------------------------------")
        lighted_member_vars = [
            attribute
            for attribute in dir(self)
            if not (attribute.startswith("__") or (attribute.startswith("__")))
        ]
        for lighted_member_var in lighted_member_vars:
            if lighted_member_var[0].isupper():
                member_value = getattr(self, lighted_member_var)
                member_type = type(member_value)
                converters: dict[typing.Type, typing.Callable] = {
                    bool: str,
                    int: str,
                    float: str,
                    str: _value,
                    type: _type,
                    pathlib.PosixPath: str,
                }
                if member_type in converters:
                    string_value = (
                        "None"
                        if member_value is None
                        else converters[member_type](member_value)
                    )
                else:
                    string_value = _type(member_value)
                string_value = self._none_save_value_string(string_value)
                self.echo(f"{lighted_member_var}: '{string_value}'")

        echo = ("NO", "YES")[
            self.capella_diagram_cache_index_file_path.is_file()
        ]
        self.echo(f"""Capella Diagram Cache Index-File exists: {echo}""")
        echo = ("YES", "NO")[self.synchronize_config_io.closed]
        self.echo(f"""Synchronize Config-IO is open: {echo}""")

    def setup_logger(self) -> None:
        """Set the logger in the right mood."""
        max_logging_level = logging.DEBUG if self.debug else logging.WARNING
        assert isinstance(logger.parent, logging.RootLogger)
        logger.parent.setLevel(max_logging_level)
        log_formatter = logging.Formatter(
            "%(asctime)-15s - %(levelname)-8s %(message)s"
        )
        console_handler = logging.StreamHandler()
        console_handler.setLevel(max_logging_level)
        console_handler.setFormatter(log_formatter)
        console_handler.addFilter(
            lambda record: record.name.startswith("capella2polarion")
            or (record.name == "httpx" and record.levelname == "INFO")
        )
        logger.parent.addHandler(console_handler)

    def load_synchronize_config(self) -> None:
        """Read the sync config into SynchronizeConfigContent.

        - example in /tests/data/model_elements/config.yaml
        """
        if self.synchronize_config_io.closed:
            raise RuntimeError("synchronize config io stream is closed ")
        if not self.synchronize_config_io.readable():
            raise RuntimeError("synchronize config io stream is not readable")
        self.config.read_config_file(self.synchronize_config_io)

    def load_capella_diagram_cache_index(self) -> None:
        """Load Capella Diagram Cache index file content."""
        if not self.capella_diagram_cache_index_file_path.is_file():
            raise ValueError(
                "capella diagramm cache index.json file does not exist"
            )

        l_text_content = self.capella_diagram_cache_index_file_path.read_text(
            encoding="utf8"
        )
        self.capella_diagram_cache_index_content = json.loads(l_text_content)
