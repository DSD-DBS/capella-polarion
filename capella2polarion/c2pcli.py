# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Tool for CLI work."""
from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
import typing
from itertools import chain

import capellambse
import click
import yaml
from capellambse import cli_helpers

from capella2polarion.polarion import PolarionWorkerParams

GLogger = logging.getLogger(__name__)


class C2PCli:
    """Call todo @AS."""

    def __init__(
        self,
        debug: bool,
        polarion_project_id: str,
        polarion_url: str,
        polarion_pat: str,
        polarion_delete_work_items: bool,
        capella_diagram_cache_folder_path: pathlib.Path,
        capella_model: cli_helpers.ModelCLI,
        synchronize_config_io: typing.TextIO,
    ) -> None:
        self.debug = debug
        self.polarion_params = PolarionWorkerParams(
            polarion_project_id,
            polarion_url,
            polarion_pat,
            polarion_delete_work_items,
        )
        self.capella_diagram_cache_folder_path = (
            capella_diagram_cache_folder_path
        )
        self.capella_diagram_cache_index_content: list[
            dict[str, typing.Any]
        ] | None = None
        self.capella_model: capellambse.MelodyModel = capella_model
        self.synchronize_config_io: typing.TextIO = synchronize_config_io
        self.synchronize_config_content: dict[str, typing.Any]
        self.synchronize_config_roles: dict[str, list[str]] | None = None
        self.echo = click.echo
        self.logger: logging.Logger

    def _noneSaveValueString(self, value: str | None) -> str | None:
        return "None" if value is None else value

    def printState(self) -> None:
        """Print the State of the cli tool."""

        def _type(aValue):
            return f"type: {type(aValue)}"

        def _value(aValue):
            return aValue

        self.echo("---------------------------------------")
        lighted_member_vars = [
            lAttribute
            for lAttribute in dir(self)
            if not (
                lAttribute.startswith("__") or (lAttribute.startswith("__"))
            )
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
                string_value = self._noneSaveValueString(string_value)
                self.echo(f"{lighted_member_var}: '{string_value}'")
        self.echo(
            f"""Capella Diagram Cache Index-File exits: {('YES'
            if self.exitsCapellaDiagrammCacheIndexFile() else 'NO')}"""
        )
        self.echo(
            f"""Synchronize Config-IO is open: {('YES'
            if not self.synchronize_config_io.closed else 'NO')}"""
        )

    def setup_logger(self) -> None:
        """Set the logger in the right mood."""
        max_logging_level = logging.DEBUG if self.debug else logging.WARNING
        assert isinstance(GLogger.parent, logging.RootLogger)
        GLogger.parent.setLevel(max_logging_level)
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
        GLogger.parent.addHandler(console_handler)
        self.logger = GLogger

    def load_synchronize_config(self) -> None:
        """Read the sync config into SynchronizeConfigContent.

        - example in /tests/data/model_elements/config.yaml
        """
        if self.synchronize_config_io.closed:
            raise Exception(f"synchronize config io stream is closed ")
        if not self.synchronize_config_io.readable():
            raise Exception(f"synchronize config io stream is not readable")
        self.synchronize_config_io.seek(0)
        self.synchronize_config_content = yaml.safe_load(
            self.synchronize_config_io
        )

    def load_roles_from_synchronize_config(self) -> None:
        """Fill SynchronizeConfigRoles and correct content."""
        if self.synchronize_config_content == None:
            raise Exception("first call loadSynchronizeConfig")
        # nächste Zeile würde ich so nicht mahcen
        if special_config_asterix := self.synchronize_config_content.pop(
            "*", []
        ):
            special_config: dict[str, typing.Any] = {}
            for typ in special_config_asterix:
                if isinstance(typ, str):
                    special_config[typ] = None
                else:
                    special_config.update(typ)

            lookup: dict[str, dict[str, list[str]]] = {}
            for layer, xtypes in self.synchronize_config_content.items():
                for xt in xtypes:
                    if isinstance(xt, str):
                        item: dict[str, list[str]] = {xt: []}
                    else:
                        item = xt

                    lookup.setdefault(layer, {}).update(item)

            new_config: dict[str, typing.Any] = {}
            for layer, xtypes in self.synchronize_config_content.items():
                new_entries: list[str | dict[str, typing.Any]] = []
                for xtype in xtypes:
                    if isinstance(xtype, dict):
                        for sub_key, sub_value in xtype.items():
                            new_value = (
                                special_config.get("*", [])
                                + special_config.get(sub_key, [])
                                + sub_value
                            )
                            new_entries.append({sub_key: new_value})
                    else:
                        star = special_config.get("*", [])
                        special_xtype = special_config.get(xtype, [])
                        if new_value := star + special_xtype:
                            new_entries.append({xtype: new_value})
                        else:
                            new_entries.append(xtype)

                wildcard_values = special_config.get("*", [])
                for key, value in special_config.items():
                    if key == "*":
                        continue

                    if isinstance(value, list):
                        new_value = (
                            lookup.get(layer, {}).get(key, [])
                            + wildcard_values
                            + value
                        )
                        new_entries.append({key: new_value})
                    elif value is None and key not in [
                        entry
                        if isinstance(entry, str)
                        else list(entry.keys())[0]
                        for entry in new_entries
                    ]:
                        new_entries.append({key: wildcard_values})
                new_config[layer] = new_entries
            self.synchronize_config_content = new_config

        roles: dict[str, list[str]] = {}
        for typ in chain.from_iterable(
            self.synchronize_config_content.values()
        ):
            if isinstance(typ, dict):
                for key, role_ids in typ.items():
                    roles[key] = list(role_ids)
            else:
                roles[typ] = []
        self.synchronize_config_roles = roles

    def get_capella_diagram_cache_index_file_path(self) -> pathlib.Path:
        """Return index file path."""
        if self.capella_diagram_cache_folder_path == None:
            raise Exception("CapellaDiagramCacheFolderPath not filled")
        return self.capella_diagram_cache_folder_path / "index.json"

    def exitsCapellaDiagrammCacheIndexFile(self) -> bool:
        """Test existens of file."""
        return (
            False
            if self.get_capella_diagram_cache_index_file_path() == None
            else self.get_capella_diagram_cache_index_file_path().is_file()
        )

    def load_capella_diagramm_cache_index(self) -> None:
        """Load to CapellaDiagramCacheIndexContent."""
        if not self.exitsCapellaDiagrammCacheIndexFile():
            raise Exception("capella diagramm cache index file doe not exits")
        self.capella_diagram_cache_index_content = None
        if self.get_capella_diagram_cache_index_file_path() != None:
            l_text_content = (
                self.get_capella_diagram_cache_index_file_path().read_text(
                    encoding="utf8"
                )
            )
            self.capella_diagram_cache_index_content = json.loads(
                l_text_content
            )
