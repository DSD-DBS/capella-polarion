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
    envvar="POLARION_HOST",
    type=str,
)
@click.option("--polarion-pat", envvar="POLARION_PAT", type=str)
@click.option("--polarion-delete-work-items", is_flag=True, default=False)
@click.option("--capella-model", type=cli_helpers.ModelCLI(), default=None)
@click.pass_context
def cli(
    ctx: click.core.Context,
    debug: bool,
    polarion_project_id: str,
    polarion_url: str,
    polarion_pat: str,
    polarion_delete_work_items: bool,
    capella_model: capellambse.MelodyModel,
) -> None:
    """Synchronise data from Capella to Polarion."""
    if capella_model.diagram_cache is None:
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
    default=None,
)
@click.option("--force-update", is_flag=True, default=False)
@click.option("--type-prefix", type=str, default="")
@click.option("--role-prefix", type=str, default="")
@click.pass_context
def synchronize(
    ctx: click.core.Context,
    force_update: bool,
    synchronize_config: typing.TextIO,
    type_prefix: str,
    role_prefix: str,
) -> None:
    """Synchronise model elements."""
    capella_to_polarion_cli: Capella2PolarionCli = ctx.obj
    logger.info(
        "Synchronising model elements to Polarion project with id %s...",
        capella_to_polarion_cli.polarion_params.project_id,
    )
    capella_to_polarion_cli.load_synchronize_config(synchronize_config)
    capella_to_polarion_cli.force_update = force_update
    capella_to_polarion_cli.type_prefix = type_prefix
    capella_to_polarion_cli.role_prefix = role_prefix

    converter = model_converter.ModelConverter(
        capella_to_polarion_cli.capella_model,
        capella_to_polarion_cli.polarion_params.project_id,
        type_prefix=capella_to_polarion_cli.type_prefix,
        role_prefix=capella_to_polarion_cli.role_prefix,
    )

    converter.read_model(capella_to_polarion_cli.config)

    polarion_worker = pw.CapellaPolarionWorker(
        capella_to_polarion_cli.polarion_params,
        capella_to_polarion_cli.force_update,
    )

    polarion_worker.load_polarion_work_item_map()

    converter.generate_work_items(polarion_worker.polarion_data_repo)

    polarion_worker.delete_orphaned_work_items(converter.converter_session)
    polarion_worker.create_missing_work_items(converter.converter_session)

    # Create missing links for new work items
    converter.generate_work_items(
        polarion_worker.polarion_data_repo,
        generate_links=True,
        generate_attachments=True,
    )

    polarion_worker.compare_and_update_work_items(converter.converter_session)


@cli.command()
@click.option(
    "--document-rendering-config",
    type=click.File(mode="r", encoding="utf8"),
    default=None,
)
@click.option("--overwrite-layouts", is_flag=True, default=False)
@click.option("--overwrite-numbering", is_flag=True, default=False)
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

    polarion_worker.load_polarion_work_item_map()

    configs = document_config.read_config_file(
        document_rendering_config, capella_to_polarion_cli.capella_model
    )
    renderer = document_renderer.DocumentRenderer(
        polarion_worker.polarion_data_repo,
        capella_to_polarion_cli.capella_model,
    )
    for config in configs.full_authority:
        rendering_layouts = document_config.generate_work_item_layouts(
            config.work_item_layouts
        )
        for instance in config.instances:
            if old_doc := polarion_worker.get_and_customize_document(
                instance.polarion_space,
                instance.polarion_name,
                instance.polarion_title,
                rendering_layouts if overwrite_layouts else None,
                config.heading_numbering if overwrite_numbering else None,
            ):
                new_doc, work_items = renderer.render_document(
                    config.template_directory,
                    config.template,
                    document=old_doc,
                    **instance.params,
                )
                polarion_worker.update_document(new_doc)
                polarion_worker.update_work_items(work_items)
            else:
                new_doc, _ = renderer.render_document(
                    config.template_directory,
                    config.template,
                    instance.polarion_space,
                    instance.polarion_name,
                    instance.polarion_title,
                    config.heading_numbering,
                    rendering_layouts,
                    **instance.params,
                )
                polarion_worker.post_document(new_doc)

    for config in configs.mixed_authority:
        rendering_layouts = document_config.generate_work_item_layouts(
            config.work_item_layouts
        )
        for instance in config.instances:
            old_doc = polarion_worker.get_and_customize_document(
                instance.polarion_space,
                instance.polarion_name,
                instance.polarion_title,
                rendering_layouts if overwrite_layouts else None,
                config.heading_numbering if overwrite_numbering else None,
            )
            assert old_doc is not None, (
                "Did not find document "
                f"{instance.polarion_space}/{instance.polarion_name}"
            )
            new_doc, work_items = renderer.update_mixed_authority_document(
                old_doc,
                config.template_directory,
                config.sections,
                instance.params,
                instance.section_params,
            )
            polarion_worker.update_document(new_doc)
            polarion_worker.update_work_items(work_items)


if __name__ == "__main__":
    cli(obj={})
