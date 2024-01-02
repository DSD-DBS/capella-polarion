# Copyright DB InfraGo AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Main entry point into capella2polarion."""
from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
import typing as t
from itertools import chain

import capellambse
import click
import polarion_rest_api_client as polarion_api
import yaml
from capellambse import cli_helpers

from capella2polarion import elements
from capella2polarion.elements import serialize

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
    config: dict[str, list[str | dict[str, t.Any]]],
    special: list[str | dict[str, t.Any]],
) -> dict[str, t.Any]:
    special_config: dict[str, t.Any] = {}
    for typ in special:
        if isinstance(typ, str):
            special_config[typ] = None
        else:
            special_config.update(typ)

    lookup: dict[str, dict[str, list[str]]] = {}
    for layer, xtypes in config.items():
        for xt in xtypes:
            if isinstance(xt, str):
                item: dict[str, list[str]] = {xt: []}
            else:
                item = xt

            lookup.setdefault(layer, {}).update(item)

    new_config: dict[str, t.Any] = {}
    for layer, xtypes in config.items():
        new_entries: list[str | dict[str, t.Any]] = []
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
                entry if isinstance(entry, str) else list(entry.keys())[0]
                for entry in new_entries
            ]:
                new_entries.append({key: wildcard_values})
        new_config[layer] = new_entries

    return new_config


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
        delete,
        polarion_api_endpoint=f"{ctx.obj['POLARION_HOST']}/rest/v1",
        polarion_access_token=os.environ["POLARION_PAT"],
        custom_work_item=serialize.CapellaWorkItem,
        add_work_item_checksum=True,
    )
    if not ctx.obj["API"].project_exists():
        sys.exit(1)


@cli.command()
@click.argument("model", type=cli_helpers.ModelCLI())
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
@click.argument("config_file", type=click.File(mode="r", encoding="utf8"))
@click.pass_context
def model_elements(
    ctx: click.core.Context,
    model: capellambse.MelodyModel,
    diagram_cache: pathlib.Path,
    config_file: t.TextIO,
) -> None:
    """Synchronise model elements."""
    logger.info(
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

    logger.info(
        "Synchronising model elements (%r) to Polarion project with id %r...",
        str(elements.ELEMENTS_IDX_PATH),
        ctx.obj["PROJECT_ID"],
    )
    ctx.obj["MODEL"] = model
    ctx.obj["CONFIG"] = yaml.safe_load(config_file)
    ctx.obj["ROLES"] = _get_roles_from_config(ctx.obj)
    (
        ctx.obj["ELEMENTS"],
        ctx.obj["POLARION_TYPE_MAP"],
    ) = elements.get_elements_and_type_map(ctx.obj)
    ctx.obj["CAPELLA_UUIDS"] = set(ctx.obj["POLARION_TYPE_MAP"])
    ctx.obj["TYPES"] = elements.get_types(ctx.obj)
    ctx.obj["POLARION_WI_MAP"] = elements.get_polarion_wi_map(ctx.obj)
    ctx.obj["POLARION_ID_MAP"] = {
        uuid: wi.id for uuid, wi in ctx.obj["POLARION_WI_MAP"].items()
    }
    duuids = {
        diag["uuid"] for diag in ctx.obj["DIAGRAM_IDX"] if diag["success"]
    }
    ctx.obj["ELEMENTS"]["Diagram"] = [
        diag for diag in ctx.obj["ELEMENTS"]["Diagram"] if diag.uuid in duuids
    ]

    elements.element.create_work_items(ctx.obj)
    elements.delete_work_items(ctx.obj)
    elements.post_work_items(ctx.obj)

    # Create missing links b/c of unresolved references
    elements.element.create_work_items(ctx.obj)
    elements.patch_work_items(ctx.obj)


if __name__ == "__main__":
    cli(obj={})
