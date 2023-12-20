# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Main entry point into capella2polarion."""
from __future__ import annotations

import pathlib
import typing

import click
from capellambse import cli_helpers

from capella2polarion.c2pcli import C2PCli
from capella2polarion.c2polarion import PolarionWorker
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
    lC2PCli.setup_logger()
    ctx.obj = lC2PCli
    lC2PCli.echo = click.echo
    lC2PCli.echo("Start")


@cli.command()
@click.pass_obj
def printCliState(aC2PCli: C2PCli) -> None:
    """Print the CLI State."""
    aC2PCli.setup_logger()
    aC2PCli.print_state()


@cli.command()
@click.pass_context
def synchronize(ctx: click.core.Context) -> None:
    """Synchronise model elements."""
    capella_to_polarion_cli: C2PCli = ctx.obj
    capella_to_polarion_cli.logger.info(
        f"""
Synchronising diagrams from diagram cache at
'{str(capella_to_polarion_cli.get_capella_diagram_cache_index_file_path())}'
to Polarion project with id
{capella_to_polarion_cli.polarion_params.project_id}...
        """
    )
    capella_to_polarion_cli.load_synchronize_config()
    capella_to_polarion_cli.load_roles_from_synchronize_config()
    capella_to_polarion_cli.load_capella_diagramm_cache_index()
    polarion_worker = PolarionWorker(
        capella_to_polarion_cli.polarion_params,
        capella_to_polarion_cli.logger,
        helpers.resolve_element_type,
    )
    assert (
        capella_to_polarion_cli.capella_diagram_cache_index_content is not None
    )
    polarion_worker.load_elements_and_type_map(
        capella_to_polarion_cli.synchronize_config_content,
        capella_to_polarion_cli.capella_model,
        capella_to_polarion_cli.capella_diagram_cache_index_content,
    )
    # TODO - DEAKTIVIEREN - ACHTUNG!!!!!!
    # polarion_worker.simulation = True
    polarion_worker.fill_xtypes()
    polarion_worker.load_polarion_work_item_map()
    lDescriptionReference: typing.Any = {}
    lNewWorkItems: dict[str, serialize.CapellaWorkItem]
    lNewWorkItems = polarion_worker.create_work_items(
        capella_to_polarion_cli.capella_diagram_cache_folder_path,
        capella_to_polarion_cli.capella_model,
        lDescriptionReference,
    )
    polarion_worker.delete_work_items()
    polarion_worker.post_work_items(lNewWorkItems)
    lNewWorkItems = polarion_worker.create_work_items(
        capella_to_polarion_cli.capella_diagram_cache_folder_path,
        capella_to_polarion_cli.capella_model,
        lDescriptionReference,
    )
    polarion_worker.patch_work_items(
        capella_to_polarion_cli.capella_model,
        lNewWorkItems,
        lDescriptionReference,
        capella_to_polarion_cli.synchronize_config_roles,
    )


if __name__ == "__main__":
    cli(obj={})
