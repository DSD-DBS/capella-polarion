# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""A jinja renderer for Polarion documents."""

import dataclasses
import html
import logging
import pathlib
import typing as t

import capellambse
import jinja2
import polarion_rest_api_client as polarion_api
from lxml import etree
from lxml import html as lxmlhtml

from capella2polarion.connectors import polarion_repo

from .. import data_model
from . import document_config, polarion_html_helper
from . import text_work_item_provider as twi

AREA_END_CLS = "c2pAreaEnd"
"""This class is expected for a div in a wiki macro to start a rendering area
in mixed authority documents."""
AREA_START_CLS = "c2pAreaStart"
"""This class is expected for a div in a wiki macro to end a rendering area in
mixed authority documents."""

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class RenderingSession:
    """A data class for parameters handled during a rendering session."""

    headings: list[polarion_api.WorkItem] = dataclasses.field(
        default_factory=list
    )
    heading_ids: list[str] = dataclasses.field(default_factory=list)
    rendering_layouts: list[polarion_api.RenderingLayout] = dataclasses.field(
        default_factory=list
    )
    inserted_work_item_ids: list[str] = dataclasses.field(default_factory=list)
    text_work_items: dict[str, polarion_api.WorkItem] = dataclasses.field(
        default_factory=dict
    )
    document_project_id: str | None = None


@dataclasses.dataclass
class ProjectData:
    """A class holding data of a project which documents are rendered for."""

    new_docs: list[data_model.DocumentData] = dataclasses.field(
        default_factory=list
    )
    updated_docs: list[data_model.DocumentData] = dataclasses.field(
        default_factory=list
    )


class DocumentRenderer(polarion_html_helper.JinjaRendererMixin):
    """A Renderer class for Polarion documents."""

    def __init__(
        self,
        polarion_repository: polarion_repo.PolarionDataRepository,
        model: capellambse.MelodyModel,
        model_work_item_project_id: str,
        overwrite_heading_numbering: bool = False,
        overwrite_layouts: bool = False,
    ):
        self.polarion_repository = polarion_repository
        self.model = model
        self.jinja_envs: dict[str, jinja2.Environment] = {}
        self.overwrite_heading_numbering = overwrite_heading_numbering
        self.overwrite_layouts = overwrite_layouts
        self.projects: dict[str | None, ProjectData] = {}
        self.existing_documents: polarion_repo.DocumentRepository = {}
        self.model_work_item_project_id = model_work_item_project_id

    def setup_env(self, env: jinja2.Environment):
        """Add globals and filters to the environment."""
        env.globals["insert_work_item"] = self.__insert_work_item
        env.globals["heading"] = self.__heading
        env.globals["work_item_field"] = self.__work_item_field
        env.filters["link_work_item"] = self.__link_work_item

    def _is_external_document(self, session: RenderingSession) -> bool:
        """Check if the document is in a different project than the model."""
        if session.document_project_id is None:
            return False
        return session.document_project_id != self.model_work_item_project_id

    def __insert_work_item(
        self, obj: object, session: RenderingSession, level: int | None = None
    ) -> str:
        if (obj := self.check_model_element(obj)) is None:
            logger.error(
                "A non-model object was passed to insert a work item."
            )
            return polarion_html_helper.RED_TEXT.format(
                text="A non-model object was passed to insert a work item."
            )

        if wi := self.polarion_repository.get_work_item_by_capella_uuid(
            obj.uuid
        ):
            assert wi.id
            if wi.id in session.inserted_work_item_ids:
                logger.info(
                    "WorkItem %s is already in the document."
                    "A link will be added instead of inserting it.",
                    wi.id,
                )
                return f"<p>{self.__link_work_item(obj)}</p>"

            assert wi.type
            layout_index = polarion_html_helper.get_layout_index(
                "section", session.rendering_layouts, wi.type
            )

            custom_info = ""
            if level is not None:
                custom_info = f"level={level}|"

            session.inserted_work_item_ids.append(wi.id)
            if self._is_external_document(session):
                # pylint: disable-next=line-too-long
                return polarion_html_helper.POLARION_WORK_ITEM_DOCUMENT_PROJECT.format(
                    pid=wi.id,
                    lid=layout_index,
                    custom_info=custom_info,
                    project=self.model_work_item_project_id,
                )
            else:
                return polarion_html_helper.POLARION_WORK_ITEM_DOCUMENT.format(
                    pid=wi.id, lid=layout_index, custom_info=custom_info
                )

        return polarion_html_helper.RED_TEXT.format(
            text=f"Missing WorkItem for UUID {obj.uuid}"
        )

    def __link_work_item(self, obj: object) -> str:
        if (obj := self.check_model_element(obj)) is None:
            logger.error("A non-model object was passed to link a work item.")
            return polarion_html_helper.RED_TEXT.format(
                text="A non-model object was passed to link a work item."
            )

        if wi := self.polarion_repository.get_work_item_by_capella_uuid(
            obj.uuid
        ):
            return polarion_html_helper.POLARION_WORK_ITEM_URL_PROJECT.format(
                pid=wi.id, project=self.model_work_item_project_id
            )

        return polarion_html_helper.RED_TEXT.format(
            text=f"Missing WorkItem for {obj.xtype} {obj.name} ({obj.uuid})"
        )

    def __heading(self, level: int, text: str, session: RenderingSession):
        if session.heading_ids:
            hid = session.heading_ids.pop(0)
            session.headings.append(polarion_api.WorkItem(id=hid, title=text))
            return (
                f"<h{level} "
                f'id="{polarion_html_helper.WI_ID_PREFIX}{hid}">'
                f"</h{level}>"
            )
        return f"<h{level}>{text}</h{level}>"

    def __work_item_field(self, obj: object, field: str) -> t.Any:
        if (obj := self.check_model_element(obj)) is None:
            logger.error(
                "A non-model object was passed to get a work item field."
            )
            return "A non-model object was passed to get a work item field."

        if wi := self.polarion_repository.get_work_item_by_capella_uuid(
            obj.uuid
        ):
            return getattr(
                wi, field, f"Missing field {field} for work item {wi.id}"
            )

        return f"No work item for {obj.uuid}"

    @t.overload
    def render_document(
        self,
        template_folder: str | pathlib.Path,
        template_name: str,
        polarion_folder: str,
        polarion_name: str,
        document_title: str | None = None,
        heading_numbering: bool = False,
        rendering_layouts: list[polarion_api.RenderingLayout] | None = None,
        *,
        text_work_item_provider: twi.TextWorkItemProvider | None = None,
        document_project_id: str | None = None,
        **kwargs: t.Any,
    ) -> data_model.DocumentData:
        """Render a new Polarion document."""

    @t.overload
    def render_document(
        self,
        template_folder: str | pathlib.Path,
        template_name: str,
        *,
        document: polarion_api.Document,
        text_work_item_provider: twi.TextWorkItemProvider | None = None,
        document_project_id: str | None = None,
        **kwargs: t.Any,
    ) -> data_model.DocumentData:
        """Update an existing Polarion document."""

    def render_document(
        self,
        template_folder: str | pathlib.Path,
        template_name: str,
        polarion_folder: str | None = None,
        polarion_name: str | None = None,
        document_title: str | None = None,
        heading_numbering: bool = False,
        rendering_layouts: list[polarion_api.RenderingLayout] | None = None,
        document: polarion_api.Document | None = None,
        text_work_item_provider: twi.TextWorkItemProvider | None = None,
        document_project_id: str | None = None,
        **kwargs: t.Any,
    ) -> data_model.DocumentData:
        """Render a Polarion document."""
        text_work_item_provider = (
            text_work_item_provider or twi.TextWorkItemProvider()
        )
        if document is not None:
            polarion_folder = document.module_folder
            polarion_name = document.module_name

        assert polarion_name is not None and polarion_folder is not None, (
            "You either need to pass a folder and a name or a document with a "
            "module_folder and a module_name defined"
        )

        env = self._get_jinja_env(template_folder)
        template = env.get_template(template_name)

        session = RenderingSession(document_project_id=document_project_id)
        if document is not None:
            session.rendering_layouts = document.rendering_layouts or []
            if document.home_page_content and document.home_page_content.value:
                session.heading_ids = polarion_html_helper.extract_headings(
                    document.home_page_content.value
                )
        else:
            document = polarion_api.Document(
                title=document_title,
                module_folder=polarion_folder,
                module_name=polarion_name,
                outline_numbering=heading_numbering,
            )
            if rendering_layouts is not None:
                session.rendering_layouts = rendering_layouts

        rendering_result = template.render(
            model=self.model, session=session, **kwargs
        )
        text_work_item_provider.generate_text_work_items(
            lxmlhtml.fragments_fromstring(rendering_result),
        )

        document.home_page_content = polarion_api.TextContent(
            "text/html",
            rendering_result,
        )
        document.rendering_layouts = session.rendering_layouts

        return data_model.DocumentData(
            document, session.headings, text_work_item_provider
        )

    def update_mixed_authority_document(
        self,
        document: polarion_api.Document,
        template_folder: str | pathlib.Path,
        sections: dict[str, str],
        global_parameters: dict[str, t.Any],
        section_parameters: dict[str, dict[str, t.Any]],
        text_work_item_provider: twi.TextWorkItemProvider | None = None,
        document_project_id: str | None = None,
    ) -> data_model.DocumentData:
        """Update a mixed authority document."""
        text_work_item_provider = (
            text_work_item_provider or twi.TextWorkItemProvider()
        )
        assert (
            document.home_page_content and document.home_page_content.value
        ), "In mixed authority the document must have content"
        html_elements = lxmlhtml.fragments_fromstring(
            document.home_page_content.value
        )

        session = RenderingSession(
            rendering_layouts=document.rendering_layouts or [],
            document_project_id=document_project_id,
        )
        section_areas = self._extract_section_areas(html_elements, session)
        env = self._get_jinja_env(template_folder)

        new_content = []
        last_section_end = 0

        for section_name, area in section_areas.items():
            if section_name not in sections:
                logger.warning(
                    "Found section %s in document, "
                    "but it is not defined in the config",
                    section_name,
                )
                continue
            new_content += html_elements[last_section_end : area[0] + 1]
            last_section_end = area[1]
            current_content = html_elements[area[0] + 1 : area[1]]
            session.heading_ids = polarion_html_helper.extract_headings(
                current_content
            )
            template = env.get_template(sections[section_name])
            content = template.render(
                model=self.model,
                session=session,
                **(
                    global_parameters
                    | section_parameters.get(section_name, {})
                ),
            )
            work_item_ids = polarion_html_helper.extract_work_items(
                current_content
            )
            html_fragments = lxmlhtml.fragments_fromstring(content)
            text_work_item_provider.generate_text_work_items(
                html_fragments, work_item_ids
            )
            new_content += html_fragments

        new_content += html_elements[last_section_end:]
        new_content = polarion_html_helper.remove_table_ids(new_content)

        document.home_page_content = polarion_api.TextContent(
            "text/html",
            "\n".join(
                [
                    lxmlhtml.tostring(element).decode("utf-8")
                    for element in new_content
                ]
            ),
        )
        document.rendering_layouts = session.rendering_layouts

        return data_model.DocumentData(
            document, session.headings, text_work_item_provider
        )

    def _update_rendering_layouts(
        self,
        document: polarion_api.Document,
        rendering_layouts: list[polarion_api.RenderingLayout],
    ):
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
        space: str,
        name: str,
        title: str | None,
        rendering_layouts: list[polarion_api.RenderingLayout],
        heading_numbering: bool,
    ) -> tuple[polarion_api.Document | None, list[polarion_api.WorkItem]]:
        old_doc, text_work_items = self.existing_documents.get(
            (project_id, space, name), (None, [])
        )
        if old_doc is not None:
            if title:
                old_doc.title = title
            if self.overwrite_layouts:
                self._update_rendering_layouts(old_doc, rendering_layouts)
            if self.overwrite_heading_numbering:
                old_doc.outline_numbering = heading_numbering

        return old_doc, text_work_items

    def render_documents(
        self,
        configs: document_config.DocumentConfigs,
        existing_documents: polarion_repo.DocumentRepository,
    ) -> dict[str | None, ProjectData]:
        """Render all documents defined in the given config.

        Returns a list new documents followed by updated documents and
        work items, which need to be updated
        """
        self.existing_documents = existing_documents
        self.projects = {}

        self._render_full_authority_documents(configs.full_authority)
        self._render_mixed_authority_documents(configs.mixed_authority)

        return self.projects

    def _check_document_status(
        self,
        document: polarion_api.Document,
        config: document_config.BaseDocumentRenderingConfig,
    ):
        if (
            config.status_allow_list is not None
            and document.status not in config.status_allow_list
        ):
            logger.warning(
                "Won't update document %s/%s due to status "
                "restrictions. Status is %s and should be in %r.",
                document.module_folder,
                document.module_name,
                document.status,
                config.status_allow_list,
            )
            return False
        return True

    def _render_mixed_authority_documents(
        self,
        mixed_authority_configs: list[
            document_config.MixedAuthorityDocumentRenderingConfig
        ],
    ):
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
                    instance.polarion_space,
                    instance.polarion_name,
                    instance.polarion_title,
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
                    document_data = self.update_mixed_authority_document(
                        old_doc,
                        config.template_directory,
                        config.sections,
                        instance.params,
                        instance.section_params,
                        text_work_item_provider,
                        config.project_id,
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
    ):
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
                    instance.polarion_space,
                    instance.polarion_name,
                    instance.polarion_title,
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
                        document_data = self.render_document(
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
                        document_data = self.render_document(
                            config.template_directory,
                            config.template,
                            instance.polarion_space,
                            instance.polarion_name,
                            instance.polarion_title,
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

    def _extract_section_areas(
        self, html_elements: list[etree._Element], session: RenderingSession
    ):
        section_areas = {}
        current_area_id = None
        current_area_start = None
        for element_index, element in enumerate(html_elements):
            if (
                current_area_id is None
                and element.tag == "div"
                and (
                    matches := polarion_html_helper.WI_ID_REGEX.match(
                        element.get("id", "")
                    )
                )
            ):
                session.inserted_work_item_ids.append(matches.group(1))
                continue

            if (
                element.tag != "div"
                or element.get("class") != "polarion-dle-wiki-block"
            ):
                continue
            for child in element.iterchildren():
                if child.get("class") == "polarion-dle-wiki-block-source":
                    text = html.unescape(child.text)
                    content = lxmlhtml.fragments_fromstring(text)
                    if (
                        content
                        and not isinstance(content[0], str)
                        and content[0].tag == "div"
                    ):
                        element_id = content[0].get("id")
                        if content[0].get("class") == AREA_START_CLS:
                            assert (
                                element_id is not None
                            ), "There was no id set to identify the area"
                            assert current_area_id is None, (
                                f"Started a new area {element_id} "
                                f"while being in area {current_area_id}"
                            )
                            current_area_id = element_id
                            current_area_start = element_index
                        elif content[0].get("class") == AREA_END_CLS:
                            assert (
                                element_id is not None
                            ), "There was no id set to identify the area"
                            assert current_area_id == element_id, (
                                f"Ended area {element_id} "
                                f"while being in area {current_area_id}"
                            )
                            section_areas[current_area_id] = (
                                current_area_start,
                                element_index,
                            )
                            current_area_id = None
                            current_area_start = None
        return section_areas
