# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Main entry point into capella2polarion."""
from __future__ import annotations

import logging
import pathlib
import typing

import capellambse
import click
from capellambse import cli_helpers

from capella2polarion.cli import Capella2PolarionCli
from capella2polarion.connectors import polarion_worker as pw
from capella2polarion.converters import model_converter

logger = logging.getLogger(__name__)


@click.group()
@click.option("--debug", is_flag=True, default=False)
@click.option("--force-update", is_flag=True, default=False)
@click.option(
    "--polarion-project-id",
    type=str,
    required=False,
    default=None,
    envvar="POLARION_PROJECT_ID",
)
@click.option(
    "--polarion-url",
    envvar="POLARION_HOST",
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
    force_update: bool,
    polarion_project_id: str,
    polarion_url: str,
    polarion_pat: str,
    polarion_delete_work_items: bool,
    capella_diagram_cache_folder_path: pathlib.Path,
    capella_model: capellambse.MelodyModel,
    synchronize_config: typing.TextIO,
) -> None:
    """Synchronise data from Capella to Polarion."""
    capella2polarion_cli = Capella2PolarionCli(
        debug,
        polarion_project_id,
        polarion_url,
        polarion_pat,
        polarion_delete_work_items,
        capella_diagram_cache_folder_path,
        capella_model,
        synchronize_config,
        force_update,
    )
    capella2polarion_cli.setup_logger()
    ctx.obj = capella2polarion_cli


@cli.command()
@click.pass_obj
def print_cli_state(capella2polarion_cli: Capella2PolarionCli) -> None:
    """Print the CLI State."""
    capella2polarion_cli.setup_logger()
    capella2polarion_cli.print_state()


@cli.command()
@click.pass_context
def synchronize(ctx: click.core.Context) -> None:
    """Synchronise model elements."""
    capella_to_polarion_cli: Capella2PolarionCli = ctx.obj
    logger.info(
        "Synchronising diagrams from diagram cache at "
        "%s to Polarion project with id %s...",
        str(capella_to_polarion_cli.capella_diagram_cache_folder_path),
        capella_to_polarion_cli.polarion_params.project_id,
    )
    capella_to_polarion_cli.load_synchronize_config()
    capella_to_polarion_cli.load_capella_diagram_cache_index()

    assert (
        capella_to_polarion_cli.capella_diagram_cache_index_content is not None
    )

    converter = model_converter.ModelConverter(
        capella_to_polarion_cli.capella_model,
        capella_to_polarion_cli.capella_diagram_cache_folder_path,
        capella_to_polarion_cli.polarion_params.project_id,
    )

    converter.read_model(
        capella_to_polarion_cli.config,
        capella_to_polarion_cli.capella_diagram_cache_index_content,
    )

    polarion_worker = pw.CapellaPolarionWorker(
        capella_to_polarion_cli.polarion_params,
        capella_to_polarion_cli.config,
        capella_to_polarion_cli.force_update,
    )

    polarion_worker.load_polarion_work_item_map()

    converter.generate_work_items(polarion_worker.polarion_data_repo)

    polarion_worker.delete_work_items(converter.converter_session)
    polarion_worker.post_work_items(converter.converter_session)

    # Create missing links for new work items
    converter.generate_work_items(polarion_worker.polarion_data_repo, True)

    polarion_worker.patch_work_items(converter.converter_session)


if __name__ == "__main__":
    cli(obj={})
