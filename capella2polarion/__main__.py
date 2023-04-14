# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Main entry point into capella2polarion."""

import json
import logging
import os
import pathlib
import sys
import typing as t
from itertools import chain

import capellambse
import click
import yaml
from capellambse import cli_helpers

from capella2polarion import elements, polarion_api

logger = logging.getLogger(__name__)


def _read_and_check_environment_vars(ctx: click.core.Context) -> None:
    if pathlib.Path(".env").is_file():
        try:
            import dotenv

            dotenv.load_dotenv(".env")
        except ImportError:
            logger.warning(
                "Install the optional 'dev' project dependencies if you want "
                "to load environment variables from the '.env' file!"
            )

    ctx.obj["POLARION_HOST"] = os.getenv("POLARION_HOST", "")
    if not ctx.obj["POLARION_HOST"]:
        logger.error(
            "Cannot read the host URL for the Polarion server! "
            "Tried to read the environment variable 'POLARION_HOST'."
        )
        sys.exit(1)

    if not os.getenv("POLARION_PAT", ""):
        logger.error(
            "Cannot read the Personal Access Token (PAT) for the Polarion "
            "server! Tried to read the environment variable 'POLARION_PAT'."
        )
        sys.exit(1)


def _set_up_logger(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.WARNING
    assert isinstance(logger.parent, logging.RootLogger)
    logger.parent.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)-15s - %(levelname)-8s %(message)s"
    )
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(
        lambda record: record.name.startswith("capella2polarion")
        or (record.name == "httpx" and record.levelname == "INFO")
    )
    logger.parent.addHandler(console_handler)


def _get_roles_from_config(ctx: dict[str, t.Any]) -> dict[str, list[str]]:
    if special_config := ctx["CONFIG"].pop("*", []):
        ctx["CONFIG"] = _sanitize_config(ctx["CONFIG"], special_config)

    roles: dict[str, list[str]] = {}
    for typ in chain.from_iterable(ctx["CONFIG"].values()):
        if isinstance(typ, dict):
            for key, role_ids in typ.items():
                roles[key] = list(role_ids)
        else:
            roles[typ] = []
    return roles


def _sanitize_config(
    config: dict[str, list[str | dict[str, t.Any]]], special: dict[str, t.Any]
) -> dict[str, t.Any]:
    new_config: dict[str, t.Any] = {}
    for layer, xtypes in config.items():
        new_entries: list[str | dict[str, t.Any]] = []
        for xtype in xtypes:
            if isinstance(xtype, dict):
                for sub_key, sub_value in xtype.items():
                    new_value = (
                        special.get("*", [])
                        + special.get(sub_key, [])
                        + sub_value
                    )
                    new_entries.append({sub_key: new_value})
            else:
                if new_value := special.get("*", []) + special.get(xtype, []):
                    new_entries.append({xtype: new_value})
                else:
                    new_entries.append(xtype)
        new_config[layer] = new_entries

    return new_config


def get_polarion_id_map(
    ctx: dict[str, t.Any], type_: str = ""
) -> dict[str, str]:
    """Map workitem IDs to Capella UUID or empty string if not set."""
    types_ = map(elements.helpers.resolve_element_type, ctx.get("TYPES", []))
    types = [type_] if type_ else list(types_)
    return ctx["API"].get_work_item_element_mapping(types)


@click.group()
@click.option("--debug/--no-debug", is_flag=True, default=False)
@click.option("--project-id", required=True, type=str)
@click.option("--delete", is_flag=True, default=False)
@click.pass_context
def cli(
    ctx: click.core.Context, debug: bool, project_id: str, delete: bool = False
) -> None:
    """Synchronise data from Capella to Polarion.

    PROJECT_ID is a Polarion project id
    """
    ctx.ensure_object(dict)
    _read_and_check_environment_vars(ctx)
    _set_up_logger(debug)
    ctx.obj["PROJECT_ID"] = project_id
    ctx.obj["API"] = polarion_api.OpenAPIPolarionProjectClient(
        project_id,
        capella_uuid_attribute=elements.UUID_ATTR_NAME,
        delete_polarion_work_items=delete,
        polarion_api_endpoint=f"{ctx.obj['POLARION_HOST']}/rest/v1",
        polarion_access_token=os.environ["POLARION_PAT"],
    )
    if not ctx.obj["API"].project_exists():
        sys.exit(1)


@cli.command()
@click.argument(
    "diagram_cache",
    type=click.Path(
        exists=True,
        file_okay=False,
        readable=True,
        resolve_path=True,
        path_type=pathlib.Path,
    ),
)
@click.pass_context
def diagrams(ctx: click.core.Context, diagram_cache: pathlib.Path) -> None:
    """Synchronise diagrams."""
    logger.debug(
        "Synchronising diagrams from diagram cache at '%s' "
        "to Polarion project with id %r...",
        diagram_cache,
        ctx.obj["PROJECT_ID"],
    )
    idx_file = diagram_cache / "index.json"
    if not idx_file.is_file():
        logger.error("Cannot find diagram cache index file '%s'!", idx_file)
        sys.exit(1)

    ctx.obj["DIAGRAM_CACHE"] = diagram_cache
    ctx.obj["DIAGRAM_IDX"] = json.loads(idx_file.read_text(encoding="utf8"))
    ctx.obj["CAPELLA_UUIDS"] = [
        d["uuid"] for d in ctx.obj["DIAGRAM_IDX"] if d["success"]
    ]
    ctx.obj["POLARION_ID_MAP"] = get_polarion_id_map(ctx.obj, "diagram")

    elements.delete_work_items(ctx.obj)
    elements.diagram.update_diagrams(ctx.obj)
    elements.diagram.create_diagrams(ctx.obj)


@cli.command()
@click.argument("model", type=cli_helpers.ModelCLI())
@click.argument("config_file", type=click.File(mode="r", encoding="utf8"))
@click.pass_context
def model_elements(
    ctx: click.core.Context,
    model: capellambse.MelodyModel,
    config_file: t.TextIO,
) -> None:
    """Synchronise model elements."""
    ctx.obj["MODEL"] = model
    ctx.obj["CONFIG"] = yaml.safe_load(config_file)
    ctx.obj["ROLES"] = _get_roles_from_config(ctx.obj)
    (
        ctx.obj["ELEMENTS"],
        ctx.obj["POLARION_TYPE_MAP"],
    ) = elements.get_elements_and_type_map(ctx.obj)
    ctx.obj["CAPELLA_UUIDS"] = set(ctx.obj["POLARION_TYPE_MAP"])
    ctx.obj["TYPES"] = elements.get_types(ctx.obj)
    ctx.obj["POLARION_ID_MAP"] = get_polarion_id_map(ctx.obj)

    elements.delete_work_items(ctx.obj)
    elements.element.update_work_items(ctx.obj)
    elements.element.create_work_items(ctx.obj)

    ctx.obj["POLARION_ID_MAP"] = get_polarion_id_map(ctx.obj)
    elements.element.update_links(ctx.obj)

    ctx.obj["POLARION_ID_MAP"] |= get_polarion_id_map(ctx.obj, "diagram")
    _diagrams = [
        diagram
        for diagram in model.diagrams
        if diagram.uuid in ctx.obj["POLARION_ID_MAP"]
    ]
    ctx.obj["ROLES"]["Diagram"] = ["diagram_elements"]
    elements.element.update_links(ctx.obj, _diagrams)

    elements_index_file = elements.make_model_elements_index(ctx.obj)
    logger.debug(
        "Synchronising model objects (%r) to Polarion project with id %r...",
        str(elements_index_file),
        ctx.obj["PROJECT_ID"],
    )


if __name__ == "__main__":
    cli(obj={})
