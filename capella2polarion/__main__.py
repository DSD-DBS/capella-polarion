# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Main entry point into capella2polarion."""
from __future__ import annotations

import logging
import typing

import capellambse
import click
from capellambse import cli_helpers

from capella2polarion.cli import Capella2PolarionCli
from capella2polarion.connectors import polarion_worker as pw
from capella2polarion.converters import (
    document_config,
    document_renderer,
    model_converter,
)

logger = logging.getLogger(__name__)


@click.group()
@click.option(
    "--capella-model",
    type=cli_helpers.ModelCLI(),
    required=True,
    envvar="CAPELLA2POLARION_CAPELLA_MODEL",
)
@click.option(
    "--polarion-project-id",
    type=str,
    required=True,
    envvar="CAPELLA2POLARION_PROJECT_ID",
)
@click.option(
    "--polarion-url",
    type=str,
    required=True,
    envvar="POLARION_HOST",
)
@click.option("--polarion-pat", type=str, required=True, envvar="POLARION_PAT")
@click.option(
    "--polarion-delete-work-items",
    is_flag=True,
    default=False,
    envvar="CAPELLA2POLARION_DELETE_WORK_ITEMS",
)
@click.option(
    "--debug", is_flag=True, envvar="CAPELLA2POLARION_DEBUG", default=False
)
@click.pass_context
def cli(
    ctx: click.core.Context,
    capella_model: capellambse.MelodyModel | None,
    polarion_project_id: str,
    polarion_url: str,
    polarion_pat: str,
    polarion_delete_work_items: bool,
    debug: bool,
) -> None:
    """Synchronise data from Capella to Polarion."""
    if capella_model is not None and capella_model.diagram_cache is None:
        logger.warning("It's highly recommended to define a diagram cache!")

    capella2polarion_cli = Capella2PolarionCli(
        debug,
        polarion_project_id,
        polarion_url,
        polarion_pat,
        polarion_delete_work_items,
        capella_model,
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
@click.option(
    "--synchronize-config",
    type=click.File(mode="r", encoding="utf8"),
    required=True,
    envvar="CAPELLA2POLARION_SYNCHRONIZE_CONFIG",
)
@click.option(
    "--force-update",
    is_flag=True,
    envvar="CAPELLA2POLARION_FORCE_UPDATE",
    default=False,
)
@click.option(
    "--type-prefix",
    type=str,
    envvar="CAPELLA2POLARION_TYPE_PREFIX",
    default="",
)
@click.option(
    "--role-prefix",
    type=str,
    envvar="CAPELLA2POLARION_ROLE_PREFIX",
    default="",
)
@click.option(
    "--grouped-links-custom-fields / --no-grouped-links-custom-fields",
    envvar="CAPELLA2POLARION_GROUPED_LINKS_CUSTOM_FIELDS",
    is_flag=True,
    default=True,
)
@click.pass_context
def synchronize(
    ctx: click.core.Context,
    synchronize_config: typing.TextIO,
    force_update: bool,
    type_prefix: str,
    role_prefix: str,
    grouped_links_custom_fields: bool,
) -> None:
    """Synchronise model elements."""
    capella_to_polarion_cli: Capella2PolarionCli = ctx.obj
    logger.info(
        "Synchronising model elements to Polarion project with id %s...",
        capella_to_polarion_cli.polarion_params.project_id,
    )
    capella_to_polarion_cli.load_synchronize_config(
        synchronize_config, type_prefix, role_prefix
    )
    capella_to_polarion_cli.force_update = force_update

    assert capella_to_polarion_cli.capella_model is not None
    converter = model_converter.ModelConverter(
        capella_to_polarion_cli.capella_model,
        capella_to_polarion_cli.polarion_params.project_id,
    )

    converter.read_model(capella_to_polarion_cli.config)

    polarion_worker = pw.CapellaPolarionWorker(
        capella_to_polarion_cli.polarion_params,
        capella_to_polarion_cli.force_update,
    )

    polarion_worker.load_polarion_work_item_map()

    polarion_worker.delete_orphaned_work_items(converter.converter_session)
    polarion_worker.create_missing_work_items(converter.converter_session)

    # Create missing links for new work items
    converter.generate_work_items(
        polarion_worker.polarion_data_repo,
        generate_links=True,
        generate_attachments=True,
        generate_grouped_links_custom_fields=grouped_links_custom_fields,
    )

    polarion_worker.compare_and_update_work_items(converter.converter_session)


@cli.command()
@click.option(
    "--document-rendering-config",
    type=click.File(mode="r", encoding="utf8"),
    required=True,
    envvar="CAPELLA2POLARION_DOCUMENT_CONFIG",
)
@click.option(
    "--overwrite-layouts",
    is_flag=True,
    default=False,
    envvar="CAPELLA2POLARION_OVERWRITE_LAYOUTS",
)
@click.option(
    "--overwrite-numbering",
    is_flag=True,
    default=False,
    envvar="CAPELLA2POLARION_OVERWRITE_NUMBERING",
)
@click.pass_context
def render_documents(
    ctx: click.core.Context,
    document_rendering_config: typing.TextIO,
    overwrite_layouts: bool,
    overwrite_numbering: bool,
) -> None:
    """Call this command to render documents based on a config file."""
    capella_to_polarion_cli: Capella2PolarionCli = ctx.obj
    polarion_worker = pw.CapellaPolarionWorker(
        capella_to_polarion_cli.polarion_params,
        capella_to_polarion_cli.force_update,
    )

    configs = document_config.read_config_file(
        document_rendering_config, capella_to_polarion_cli.capella_model
    )

    polarion_worker.load_polarion_work_item_map()
    documents = polarion_worker.load_polarion_documents(
        configs.iterate_documents()
    )

    assert capella_to_polarion_cli.capella_model is not None
    renderer = document_renderer.DocumentRenderer(
        polarion_worker.polarion_data_repo,
        capella_to_polarion_cli.capella_model,
        capella_to_polarion_cli.polarion_params.project_id,
        overwrite_numbering,
        overwrite_layouts,
    )

    projects_document_data = renderer.render_documents(configs, documents)
    for project, project_data in projects_document_data.items():
        polarion_worker.create_documents(project_data.new_docs, project)
        polarion_worker.update_documents(project_data.updated_docs, project)


if __name__ == "__main__":
    cli(obj={})
