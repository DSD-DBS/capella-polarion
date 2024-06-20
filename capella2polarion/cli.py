# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Tool for CLI work."""
from __future__ import annotations

import logging
import pathlib
import typing

import capellambse
import click

from capella2polarion.connectors import polarion_worker as pw
from capella2polarion.converters import converter_config

logger = logging.getLogger(__name__)


class ExitCodeHandler(logging.Handler):
    def __init__(self, determine: bool = True):
        super().__init__()
        self.determine = determine
        self.has_warning = False
        self.has_error = False

    def emit(self, record: logging.LogRecord):
        if not self.determine:
            return

        if record.levelno == logging.WARNING:
            self.has_warning = True
        elif record.levelno == logging.ERROR:
            self.has_error = True


class Capella2PolarionCli:
    """Call Level Interface."""

    exit_code_handler: ExitCodeHandler

    def __init__(
        self,
        debug: bool,
        polarion_project_id: str,
        polarion_url: str,
        polarion_pat: str,
        polarion_delete_work_items: bool,
        capella_model: capellambse.MelodyModel,
        force_update: bool = False,
        type_prefix: str = "",
        role_prefix: str = "",
        determine_exit_code_from_logs: bool = False,
    ) -> None:
        self.debug = debug
        self.polarion_params = pw.PolarionWorkerParams(
            polarion_project_id,
            polarion_url,
            polarion_pat,
            polarion_delete_work_items,
        )

        self.capella_model = capella_model
        self.config = converter_config.ConverterConfig()
        self.force_update = force_update
        self.type_prefix = type_prefix
        self.role_prefix = role_prefix
        self.determine_exit_code_from_logs = determine_exit_code_from_logs

    def _none_save_value_string(self, value: str | None) -> str | None:
        return "None" if value is None else value

    def print_state(self) -> None:
        """Print the State of the cli tool."""

        def _type(value):
            return f"type: {type(value)}"

        def _value(value):
            return value

        click.echo("---------------------------------------")
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
                click.echo(f"{lighted_member_var}: '{string_value}'")

    def setup_logger(self) -> None:
        """Set the logger in the right mood."""
        max_logging_level = logging.DEBUG if self.debug else logging.WARNING
        logging.basicConfig(
            level=max_logging_level,
            format="%(asctime)-15s - %(levelname)-8s %(message)s",
        )
        logging.getLogger("httpx").setLevel("WARNING")
        logging.getLogger("httpcore").setLevel("WARNING")
        self.exit_code_handler = ExitCodeHandler(
            self.determine_exit_code_from_logs
        )
        logging.getLogger().addHandler(self.exit_code_handler)

    def load_synchronize_config(
        self, synchronize_config_io: typing.TextIO
    ) -> None:
        """Read the sync config into SynchronizeConfigContent.

        - example in /tests/data/model_elements/config.yaml
        """
        if synchronize_config_io.closed:
            raise RuntimeError("synchronize config io stream is closed ")
        if not synchronize_config_io.readable():
            raise RuntimeError("synchronize config io stream is not readable")
        self.config.read_config_file(synchronize_config_io)
