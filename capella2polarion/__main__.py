# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Main entry point into capella2polarion."""
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
from capella2polarion.c2pcli import C2PCli
from capella2polarion.elements import helpers, serialize


@click.group()
@click.option("--debug", is_flag=True, default=False)
@click.option(
    "--polarion-project-id",
    type=str,
    required=False,
    default=None,
    envvar="POLARION_PROJECT_ID",
)
@click.option(
    "--polarion-url",
    envvar="POLARION_URL",
    default="https://localhost",
    type=str,
)
@click.option("--polarion-pat", envvar="POLARION_PAT", type=str)
@click.option("--polarion-delete-work-items", is_flag=True, default=False)
@click.option(
    "--capella-diagram-cache-folder-path",
    type=click.Path(
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        path_type=pathlib.Path,
    ),
    default=None,
)
@click.option("--capella-model", type=cli_helpers.ModelCLI(), default=None)
@click.option(
    "--synchronize-config",
    type=click.File(mode="r", encoding="utf8"),
    default=None,
)
@click.pass_context
def cli(
    ctx: click.core.Context,
    debug: bool,
    polarion_project_id: str,
    polarion_url: str,
    polarion_pat: str,
    polarion_delete_work_items: bool,
    capella_diagram_cache_folder_path: pathlib.Path,
    # capella_model_base_folder: str,
    capella_model: cli_helpers.ModelCLI,
    synchronize_config: typing.TextIO,
) -> None:
    """Synchronise data from Capella to Polarion."""
    lC2PCli = C2PCli(
        debug,
        polarion_project_id,
        polarion_url,
        polarion_pat,
        polarion_delete_work_items,
        capella_diagram_cache_folder_path,
        capella_model,
        synchronize_config,
    )
    lC2PCli.setupLogger()
    ctx.obj = lC2PCli
    lC2PCli.echo = click.echo


@cli.command()
@click.pass_obj
def printCliState(aC2PCli: C2PCli) -> None:
    """Print the CLI State."""
    aC2PCli.setupLogger()
    aC2PCli.printState()


@cli.command()
# @click.argument("model", type=cli_helpers.ModelCLI())
# @click.argument("diagram_cache", type=click.Path(exists=True,file_okay=False,readable=True,resolve_path=True,path_type=pathlib.Path))
# @click.argument("config_file", type=click.File(mode="r", encoding="utf8"))
@click.pass_context
# @click.pass_obj
def synchronize(ctx: click.core.Context) -> None:
    """Synchronise model elements."""
    aC2PCli: C2PCli = ctx.obj
    aC2PCli.logger.info(
        f"""
            Synchronising diagrams from diagram cache at '{str(aC2PCli.get_capella_diagram_cache_index_file_path())}'
            to Polarion project with id {aC2PCli.polarion_params.project_id}...
        """
    )
    # ctx.obj["DIAGRAM_CACHE"] = None # Orignal ... aDiagramCachePath ... None damit es Crashed!
    # ctx.obj["MODEL"] = model
    # ctx.obj["CONFIG"] = yaml.safe_load(config_file)
    aC2PCli.load_synchronize_config()
    # ctx.obj["ROLES"] = _get_roles_from_config(ctx.obj)
    aC2PCli.load_roles_from_synchronize_config()
    aC2PCli.load_capella_diagramm_cache_index()
    # (
    #     ctx.obj["ELEMENTS"],
    #     ctx.obj["POLARION_TYPE_MAP"],
    # ) = elements.get_elements_and_type_map(
    #     aC2PCli.SynchronizeConfigContent,
    #     aC2PCli.CapellaModel,
    #     aC2PCli.CapellaDiagramCacheIndexContent,
    # )
    # ctx.obj["CAPELLA_UUIDS"] = set(ctx.obj["POLARION_TYPE_MAP"])
    # ctx.obj["CAPELLA_UUIDS"] = set(lPW.PolarionTypeMap)
    # lPW.CapellaUUIDs = set(lPW.PolarionTypeMap)
    from polarion import PolarionWorker

    lPW = PolarionWorker(
        aC2PCli.polarion_params, aC2PCli.logger, helpers.resolve_element_type
    )
    lPW.load_elements_and_type_map(
        aC2PCli.synchronize_config_content,
        aC2PCli.capella_model,
        aC2PCli.capella_diagram_cache_index_content,
    )
    # @MH - DEAKTIVIEREN - ACHTUNG!!!!!! @AS
    lPW.simulation = True
    # types = elements.get_types(
    #     ctx.obj["POLARION_TYPE_MAP"], ctx.obj["ELEMENTS"]
    # )
    lPW.fill_xtypes()
    # ctx.obj["POLARION_WI_MAP"] = elements.get_polarion_wi_map(
    #     types, ctx.obj["API"]
    # )
    # ctx.obj["POLARION_ID_MAP"] = {
    #     uuid: wi.id for uuid, wi in ctx.obj["POLARION_WI_MAP"].items()
    # }
    # ctx.obj["POLARION_ID_MAP"] = {
    #     uuid: wi.id for uuid, wi in ctx.obj["POLARION_WI_MAP"].items()
    # }
    lPW.load_polarion_work_item_map()
    # ctx.obj["DESCR_REFERENCES"] = {}
    # new_work_items = elements.element.create_work_items(
    #     ctx.obj["ELEMENTS"],
    #     aC2PCli.CapellaDiagramCacheFolderPath,
    #     ctx.obj["POLARION_TYPE_MAP"],
    #     ctx.obj["MODEL"],
    #     ctx.obj["POLARION_ID_MAP"],
    #     ctx.obj["DESCR_REFERENCES"],
    # )
    lDescriptionReference: typing.Any = {}
    lNewWorkItems: dict[str, serialize.CapellaWorkItem]
    lNewWorkItems = lPW.create_work_items(
        aC2PCli.capella_diagram_cache_folder_path,
        aC2PCli.capella_model,
        lDescriptionReference,
    )
    # elements.delete_work_items(
    #     ctx.obj["POLARION_ID_MAP"],
    #     ctx.obj["POLARION_WI_MAP"],
    #     ctx.obj["CAPELLA_UUIDS"],
    #     ctx.obj["API"],
    # )
    lPW.delete_work_items()
    # elements.post_work_items(
    #     ctx.obj["POLARION_ID_MAP"],
    #     new_work_items,
    #     ctx.obj["POLARION_WI_MAP"],
    #     ctx.obj["API"],
    # )
    lPW.post_work_items(lNewWorkItems)
    # Create missing links b/c of unresolved references
    # new_work_items = elements.element.create_work_items(
    #     ctx.obj["ELEMENTS"],
    #     aC2PCli.CapellaDiagramCacheFolderPath,
    #     ctx.obj["POLARION_TYPE_MAP"],
    #     ctx.obj["MODEL"],
    #     ctx.obj["POLARION_ID_MAP"],
    #     ctx.obj["DESCR_REFERENCES"],
    # )
    lNewWorkItems = lPW.create_work_items(
        aC2PCli.capella_diagram_cache_folder_path,
        aC2PCli.capella_model,
        lDescriptionReference,
    )
    # elements.patch_work_items(
    #     ctx.obj["POLARION_ID_MAP"],
    #     ctx.obj["MODEL"],
    #     new_work_items,
    #     ctx.obj["POLARION_WI_MAP"],
    #     ctx.obj["API"],
    #     ctx.obj["DESCR_REFERENCES"],
    #     ctx.obj["PROJECT_ID"],
    #     ctx.obj["ROLES"],
    # )
    lPW.patch_work_items(
        aC2PCli.capella_model,
        lNewWorkItems,
        lDescriptionReference,
        aC2PCli.synchronize_config_roles,
    )


if __name__ == "__main__":
    cli(obj={})
