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
import polarion_rest_api_client as polarion_api
import validators
import yaml
from capellambse import cli_helpers

from capella2polarion import elements
from capella2polarion.elements import serialize

GLogger = logging.getLogger(__name__)


class C2PCli(object):
    """Call todo @AS."""

    def __init__(
        self,
        aDebug: bool,
        aProjectId: str,
        aPolarionUrl: str,
        aPolarionPat: str,
        aPolarionDeleteWorkItems: bool,
        capella_diagram_cache_folder_path: pathlib.Path,
        capella_model: cli_helpers.ModelCLI,
        synchronize_config_io: typing.TextIO,
    ) -> None:
        self.Debug = aDebug
        self.ProjectId = aProjectId
        self.PolarionUrl = aPolarionUrl
        self.PolarionPat = aPolarionPat
        self.PolarionDeleteWorkItems = aPolarionDeleteWorkItems
        self.PolarionClient: polarion_api.OpenAPIPolarionProjectClient | None = (
            None
        )
        self.CapellaDiagramCacheFolderPath = capella_diagram_cache_folder_path
        self.CapellaDiagramCacheIndexContent: list[
            dict[str, typing.Any]
        ] | None = None
        self.CapellaModel: cli_helpers.ModelCLI = capella_model
        self.SynchronizeConfigIO: typing.TextIO = synchronize_config_io
        self.SynchronizeConfigContent: dict[str, typing.Any]
        self.SynchronizeConfigRoles: dict[str, list[str]] | None = None
        self.echo = click.echo
        self.logger: logging.Logger

    def printState(self) -> None:
        """Print the State of the cli tool."""

        def _type(aValue):
            return f"type: {type(aValue)}"

        def _value(aValue):
            return aValue

        self.echo("---------------------------------------")
        lMyLigthedMembers = [
            lAttribute
            for lAttribute in dir(self)
            if not (
                lAttribute.startswith("__") or (lAttribute.startswith("__"))
            )
        ]
        for lMyLightedMember in lMyLigthedMembers:
            if lMyLightedMember[0].isupper():
                lValue = getattr(self, lMyLightedMember)
                lType = type(lValue)
                lConverter: dict[typing.Type, typing.Callable] = {
                    bool: str,
                    int: str,
                    float: str,
                    str: _value,
                    type: _type,
                    pathlib.PosixPath: str,
                }
                if lType in lConverter:
                    lStringValue = (
                        "None" if lValue is None else lConverter[lType](lValue)
                    )
                else:
                    lStringValue = _type(lValue)
                lStringValue = self._noneSaveValueString(lStringValue)
                self.echo(f"{lMyLightedMember}: '{lStringValue}'")
        self.echo(
            f"Capella Diagram Cache Index-File exits: {('YES' if self.exitsCapellaDiagrammCacheIndexFile() else 'NO')}"
        )
        self.echo(
            f"Synchronize Config-IO is open: {('YES' if not self.SynchronizeConfigIO.closed else 'NO')}"
        )

    def setupPolarionClient(self) -> None:
        """Instantiate the polarion client, move to PolarionWorker Class."""
        if (self.ProjectId == None) or (len(self.ProjectId) == 0):
            raise Exception(
                f"""ProjectId invalid. Value '{self._noneSaveValueString(self.ProjectId)}'"""
            )
        if validators.url(self.PolarionUrl):
            raise Exception(
                f"""Polarion URL parameter is not a valid url.
                Value {self._noneSaveValueString(self.PolarionUrl)}"""
            )
        if self.PolarionPat == None:
            raise Exception(
                f"""Polarion PAT (Personal Access Token) parameter is not a valid url. Value
                '{self._noneSaveValueString(self.PolarionPat)}'"""
            )
        self.PolarionClient = polarion_api.OpenAPIPolarionProjectClient(
            self.ProjectId,
            self.PolarionDeleteWorkItems,
            polarion_api_endpoint=f"{self.PolarionUrl}/rest/v1",
            polarion_access_token=self.PolarionPat,
            custom_work_item=serialize.CapellaWorkItem,
            add_work_item_checksum=True,
        )
        # assert self.PolarionClient is not None
        if self.PolarionClient.project_exists():
            raise Exception(
                f"Miss Polarion project with id {self._noneSaveValueString(self.ProjectId)}"
            )

    def setupLogger(self) -> None:
        """Set the logger in the right mood."""
        lMaxLoggingLevel = logging.DEBUG if self.Debug else logging.WARNING
        assert isinstance(GLogger.parent, logging.RootLogger)
        GLogger.parent.setLevel(lMaxLoggingLevel)
        lLogFormatter = logging.Formatter(
            "%(asctime)-15s - %(levelname)-8s %(message)s"
        )
        lConsoleHandler = logging.StreamHandler()
        lConsoleHandler.setLevel(lMaxLoggingLevel)
        lConsoleHandler.setFormatter(lLogFormatter)
        lConsoleHandler.addFilter(
            lambda record: record.name.startswith("capella2polarion")
            or (record.name == "httpx" and record.levelname == "INFO")
        )
        GLogger.parent.addHandler(lConsoleHandler)
        self.logger = GLogger

    def load_synchronize_config(self) -> None:
        """Read the sync config into SynchronizeConfigContent.

        - example in /tests/data/model_elements/config.yaml
        """
        if self.SynchronizeConfigIO.closed:
            raise Exception(f"synchronize config io stream is closed ")
        if not self.SynchronizeConfigIO.readable():
            raise Exception(f"synchronize config io stream is not readable")
        self.SynchronizeConfigIO.seek(0)
        self.SynchronizeConfigContent = yaml.safe_load(
            self.SynchronizeConfigIO
        )

    def load_roles_from_synchronize_config(self) -> None:
        """Fill SynchronizeConfigRoles and correct content."""
        if self.SynchronizeConfigContent == None:
            raise Exception("first call loadSynchronizeConfig")
        # nächste Zeile würde ich so nicht mahcen
        if special_config_asterix := self.SynchronizeConfigContent.pop(
            "*", []
        ):
            special_config: dict[str, typing.Any] = {}
            for typ in special_config_asterix:
                if isinstance(typ, str):
                    special_config[typ] = None
                else:
                    special_config.update(typ)

            lookup: dict[str, dict[str, list[str]]] = {}
            for layer, xtypes in self.SynchronizeConfigContent.items():
                for xt in xtypes:
                    if isinstance(xt, str):
                        item: dict[str, list[str]] = {xt: []}
                    else:
                        item = xt

                    lookup.setdefault(layer, {}).update(item)

            new_config: dict[str, typing.Any] = {}
            for layer, xtypes in self.SynchronizeConfigContent.items():
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
            self.SynchronizeConfigContent = new_config

        roles: dict[str, list[str]] = {}
        for typ in chain.from_iterable(self.SynchronizeConfigContent.values()):
            if isinstance(typ, dict):
                for key, role_ids in typ.items():
                    roles[key] = list(role_ids)
            else:
                roles[typ] = []
        self.SynchronizeConfigRoles = roles

    def get_capella_diagram_cache_index_file_path(self) -> pathlib.Path:
        """Return index file path."""
        if self.CapellaDiagramCacheFolderPath == None:
            raise Exception("CapellaDiagramCacheFolderPath not filled")
        return self.CapellaDiagramCacheFolderPath / "index.json"

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
        self.CapellaDiagramCacheIndexContent = None
        if self.get_capella_diagram_cache_index_file_path() != None:
            l_text_content = (
                self.get_capella_diagram_cache_index_file_path().read_text(
                    encoding="utf8"
                )
            )
            self.CapellaDiagramCacheIndexContent = json.loads(l_text_content)

    def _noneSaveValueString(self, aValue: str | None) -> str | None:
        return "None" if aValue is None else aValue
