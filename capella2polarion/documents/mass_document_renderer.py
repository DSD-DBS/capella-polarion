# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Provides functionalities to render multiple documents config based."""

import dataclasses
import logging

import capellambse
import polarion_rest_api_client as polarion_api

from capella2polarion import data_model, polarion_html_helper
from capella2polarion.connectors import polarion_repo
from capella2polarion.documents import (
    document_config,
    document_renderer,
)
from capella2polarion.documents import text_work_item_provider as twi

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class ProjectData:
    """A class holding data of a project which documents are rendered for."""

    new_docs: list[data_model.DocumentData] = dataclasses.field(
        default_factory=list
    )
    updated_docs: list[data_model.DocumentData] = dataclasses.field(
        default_factory=list
    )


class MassDocumentRenderer:
    """A class to render multiple documents based on configs."""

    def __init__(
        self,
        polarion_repository: polarion_repo.PolarionDataRepository,
        model: capellambse.MelodyModel,
        model_work_item_project_id: str,
        overwrite_heading_numbering: bool = False,
        overwrite_layouts: bool = False,
    ):
        self.renderer = document_renderer.DocumentRenderer(
            polarion_repository, model, model_work_item_project_id
        )
        self.overwrite_heading_numbering = overwrite_heading_numbering
        self.existing_documents: polarion_repo.DocumentRepository = {}
        self.projects: dict[str | None, ProjectData] = {}
        self.overwrite_layouts = overwrite_layouts

    def render_documents(
        self,
        configs: document_config.DocumentConfigs,
        existing_documents: polarion_repo.DocumentRepository,
    ) -> dict[str | None, ProjectData]:
        """Render all documents defined in the given config.

        Returns
        -------
        documents
            A dict mapping project ID to new and updated documents.
        """
        self.existing_documents = existing_documents
        self.projects = {}

        self._render_full_authority_documents(configs.full_authority)
        self._render_mixed_authority_documents(configs.mixed_authority)
        return self.projects

    def _render_mixed_authority_documents(
        self,
        mixed_authority_configs: list[
            document_config.MixedAuthorityDocumentRenderingConfig
        ],
    ) -> None:
        for config in mixed_authority_configs:
            rendering_layouts = document_config.generate_work_item_layouts(
                config.work_item_layouts
            )
            project_data = self.projects.setdefault(
                config.project_id, ProjectData()
            )
            for instance in config.instances:
                old_doc, text_work_items = self._get_and_customize_doc(
                    config.project_id,
                    instance,
                    rendering_layouts,
                    config.heading_numbering,
                )
                text_work_item_provider = twi.TextWorkItemProvider(
                    config.text_work_item_id_field,
                    config.text_work_item_type,
                    text_work_items,
                )
                if old_doc is None:
                    logger.error(
                        "For document %s/%s no document was found, but it's "
                        "mandatory to have one in mixed authority mode",
                        instance.polarion_space,
                        instance.polarion_name,
                    )
                    continue

                if not self._check_document_status(old_doc, config):
                    continue

                try:
                    document_data = (
                        self.renderer.update_mixed_authority_document(
                            old_doc,
                            config.template_directory,
                            config.sections,
                            instance.params,
                            instance.section_params,
                            text_work_item_provider,
                            config.project_id,
                        )
                    )
                except Exception as e:
                    logger.error(
                        "Rendering for document %s/%s failed with the "
                        "following error",
                        instance.polarion_space,
                        instance.polarion_name,
                        exc_info=e,
                    )
                    continue

                project_data.updated_docs.append(document_data)

    def _render_full_authority_documents(
        self,
        full_authority_configs: list[
            document_config.FullAuthorityDocumentRenderingConfig
        ],
    ) -> None:
        for config in full_authority_configs:
            rendering_layouts = document_config.generate_work_item_layouts(
                config.work_item_layouts
            )
            project_data = self.projects.setdefault(
                config.project_id, ProjectData()
            )
            for instance in config.instances:
                old_doc, text_work_items = self._get_and_customize_doc(
                    config.project_id,
                    instance,
                    rendering_layouts,
                    config.heading_numbering,
                )
                text_work_item_provider = twi.TextWorkItemProvider(
                    config.text_work_item_id_field,
                    config.text_work_item_type,
                    text_work_items,
                )
                if old_doc:
                    if not self._check_document_status(old_doc, config):
                        continue

                    try:
                        document_data = self.renderer.render_document(
                            config.template_directory,
                            config.template,
                            document=old_doc,
                            text_work_item_provider=text_work_item_provider,
                            document_project_id=config.project_id,
                            **instance.params,
                        )
                    except Exception as e:
                        logger.error(
                            "Rendering for document %s/%s failed with the "
                            "following error",
                            instance.polarion_space,
                            instance.polarion_name,
                            exc_info=e,
                        )
                        continue

                    project_data.updated_docs.append(document_data)
                else:
                    try:
                        document_data = self.renderer.render_document(
                            config.template_directory,
                            config.template,
                            instance.polarion_space,
                            instance.polarion_name,
                            instance.polarion_title,
                            instance.polarion_type,
                            config.heading_numbering,
                            rendering_layouts,
                            text_work_item_provider=text_work_item_provider,
                            document_project_id=config.project_id,
                            **instance.params,
                        )
                    except Exception as e:
                        logger.error(
                            "Rendering for document %s/%s failed with the "
                            "following error",
                            instance.polarion_space,
                            instance.polarion_name,
                            exc_info=e,
                        )
                        continue

                    project_data.new_docs.append(document_data)

    def _update_rendering_layouts(
        self,
        document: polarion_api.Document,
        rendering_layouts: list[polarion_api.RenderingLayout],
    ) -> None:
        """Keep existing work item layouts in their original order."""
        document.rendering_layouts = document.rendering_layouts or []
        for rendering_layout in rendering_layouts:
            assert rendering_layout.type is not None
            index = polarion_html_helper.get_layout_index(
                "section", document.rendering_layouts, rendering_layout.type
            )
            document.rendering_layouts[index] = rendering_layout

    def _get_and_customize_doc(
        self,
        project_id: str | None,
        section: document_config.DocumentRenderingInstance,
        rendering_layouts: list[polarion_api.RenderingLayout],
        heading_numbering: bool,
    ) -> tuple[polarion_api.Document | None, list[polarion_api.WorkItem]]:
        old_doc, text_work_items = self.existing_documents.get(
            (project_id, section.polarion_space, section.polarion_name),
            (None, []),
        )
        if old_doc is not None:
            old_doc = polarion_api.Document(
                id=old_doc.id,
                module_folder=old_doc.module_folder,
                module_name=old_doc.module_name,
                status=old_doc.status,
                home_page_content=old_doc.home_page_content,
                rendering_layouts=old_doc.rendering_layouts,
            )
            if section.polarion_title:
                old_doc.title = section.polarion_title
            if section.polarion_type:
                old_doc.type = section.polarion_type
            if self.overwrite_layouts:
                self._update_rendering_layouts(old_doc, rendering_layouts)
            if self.overwrite_heading_numbering:
                old_doc.outline_numbering = heading_numbering

        return old_doc, text_work_items

    def _check_document_status(
        self,
        document: polarion_api.Document,
        config: document_config.BaseDocumentRenderingConfig,
    ) -> bool:
        status = document.status
        document.status = None
        if (
            config.status_allow_list is not None
            and status not in config.status_allow_list
        ):
            logger.warning(
                "Won't update document %s/%s due to status "
                "restrictions. Status is %s and should be in %r.",
                document.module_folder,
                document.module_name,
                status,
                config.status_allow_list,
            )
            return False
        return True
