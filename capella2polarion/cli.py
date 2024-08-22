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


class Capella2PolarionCli:
    """Call Level Interface."""

    def __init__(
        self,
        debug: bool,
        polarion_project_id: str,
        polarion_url: str,
        polarion_pat: str,
        polarion_delete_work_items: bool,
        capella_model: capellambse.MelodyModel,
        force_update: bool = False,
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

    def load_synchronize_config(
        self,
        synchronize_config_io: typing.TextIO,
        type_prefix: str = "",
        role_prefix: str = "",
    ) -> None:
        """Read the sync config into SynchronizeConfigContent.

        - example in /tests/data/model_elements/config.yaml
        """
        if synchronize_config_io.closed:
            raise RuntimeError("synchronize config io stream is closed ")
        if not synchronize_config_io.readable():
            raise RuntimeError("synchronize config io stream is not readable")
        self.config.read_config_file(
            synchronize_config_io, type_prefix, role_prefix
        )
