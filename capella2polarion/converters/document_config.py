# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module with classes and a loader for document rendering configs."""
import logging
import pathlib
import typing as t

import capellambse
import jinja2
import polarion_rest_api_client as polarion_api
import pydantic
import yaml

from capella2polarion import data_models
from capella2polarion.converters import polarion_html_helper

logger = logging.getLogger(__name__)


class WorkItemLayout(pydantic.BaseModel):
    """Configuration for rendering layouts of work items."""

    show_description: bool = True
    show_title: bool = True
    show_fields_as_table: bool = True
    fields_at_start: list[str] = pydantic.Field(default_factory=list)
    fields_at_end: list[str] = pydantic.Field(default_factory=list)


class DocumentRenderingInstance(pydantic.BaseModel):
    """An instance of a document that should be created in Polarion."""

    polarion_space: str
    polarion_name: str
    polarion_title: str | None = None
    params: dict[str, t.Any] = pydantic.Field(default_factory=dict)


class SectionBasedDocumentRenderingInstance(DocumentRenderingInstance):
    """An instance of a mixed authority doc with section specific params."""

    section_params: dict[str, dict[str, t.Any]] = pydantic.Field(
        default_factory=dict
    )


class BaseDocumentRenderingConfig(pydantic.BaseModel):
    """A template config, which can result in multiple Polarion documents."""

    template_directory: str | pathlib.Path
    project_id: str | None = None
    text_work_item_type: str = polarion_html_helper.TEXT_WORK_ITEM_TYPE
    text_work_item_id_field: str = polarion_html_helper.TEXT_WORK_ITEM_ID_FIELD
    status_allow_list: list[str] | None = None
    heading_numbering: bool = False
    work_item_layouts: dict[str, WorkItemLayout] = pydantic.Field(
        default_factory=dict
    )
    instances: list[DocumentRenderingInstance]


class FullAuthorityDocumentRenderingConfig(BaseDocumentRenderingConfig):
    """Full authority document config with one template per document."""

    template: str


class MixedAuthorityDocumentRenderingConfig(BaseDocumentRenderingConfig):
    """Mixed authority document with multiple auto generated sections."""

    sections: dict[str, str]
    instances: list[SectionBasedDocumentRenderingInstance]


class DocumentConfigs(pydantic.BaseModel):
    """The overall document configuration repository."""

    full_authority: list[FullAuthorityDocumentRenderingConfig] = (
        pydantic.Field(default_factory=list)
    )
    mixed_authority: list[MixedAuthorityDocumentRenderingConfig] = (
        pydantic.Field(default_factory=list)
    )

    def iterate_documents(self) -> t.Iterator[data_models.DocumentInfo]:
        """Yield all document paths of the config as tuples."""
        for conf in self.full_authority + self.mixed_authority:
            for inst in conf.instances:
                yield data_models.DocumentInfo(
                    project_id=conf.project_id,
                    module_folder=inst.polarion_space,
                    module_name=inst.polarion_name,
                    text_work_item_type=conf.text_work_item_type,
                    text_work_item_id_field=conf.text_work_item_id_field,
                )


def read_config_file(
    config: t.TextIO, model: capellambse.MelodyModel | None = None
) -> DocumentConfigs:
    """Read a yaml containing a list of DocumentRenderingConfigs."""
    if config.name.endswith(".j2"):
        assert model is not None, "For jinja configs the model is mandatory"
        template = jinja2.Template(config.read())
        config_content = yaml.safe_load(template.render(model=model))
    else:
        config_content = yaml.safe_load(config)
    if isinstance(config_content, list):
        config_content = {"full_authority": config_content}
    return DocumentConfigs(**config_content)


def generate_work_item_layouts(
    configs: dict[str, WorkItemLayout]
) -> list[polarion_api.RenderingLayout]:
    """Create polarion_api.RenderingLayouts for a given configuration."""
    results = []
    for _type, conf in configs.items():
        if conf.show_title and conf.show_description:
            layouter = polarion_api.data_models.Layouter.SECTION
        elif conf.show_description:
            layouter = polarion_api.data_models.Layouter.PARAGRAPH
        else:
            if not conf.show_title:
                logger.warning(
                    "Either the title or the description must be shown."
                    "For that reason, the title will be shown for %s.",
                    _type,
                )
            layouter = polarion_api.data_models.Layouter.TITLE
        results.append(
            polarion_api.RenderingLayout(
                type=_type,
                layouter=layouter,
                label=polarion_html_helper.camel_case_to_words(_type),
                properties=polarion_api.data_models.RenderingProperties(
                    fields_at_start=conf.fields_at_start,
                    fields_at_end=conf.fields_at_end,
                    fields_at_end_as_table=conf.show_fields_as_table,
                    hidden=True,
                    sidebar_work_item_fields=conf.fields_at_start
                    + conf.fields_at_end,
                ),
            )
        )

    return results
