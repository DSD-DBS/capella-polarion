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
from lxml import html as lxmlhtml

from capella2polarion import data_model, polarion_html_helper
from capella2polarion.connectors import polarion_repo
from capella2polarion.documents import text_work_item_provider as twi

PROJ_WI_PAIR_LEN = 2

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

    document_project_id: str

    headings: list[polarion_api.WorkItem] = dataclasses.field(
        default_factory=list
    )
    heading_ids: list[str] = dataclasses.field(default_factory=list)
    rendering_layouts: list[polarion_api.RenderingLayout] = dataclasses.field(
        default_factory=list
    )
    inserted_work_item_ids: list[tuple[str, str]] = dataclasses.field(
        default_factory=list
    )
    text_work_items: dict[str, polarion_api.WorkItem] = dataclasses.field(
        default_factory=dict
    )


class DocumentRenderer(polarion_html_helper.JinjaRendererMixin):
    """A Renderer class for Polarion documents."""

    def __init__(
        self,
        polarion_repository: polarion_repo.PolarionDataRepository,
        model: capellambse.MelodyModel,
        model_work_item_project_id: str,
    ):
        self.polarion_repository = polarion_repository
        self.model = model
        self.jinja_envs: dict[str, jinja2.Environment] = {}
        self.model_work_item_project_id = model_work_item_project_id

    def setup_env(self, env: jinja2.Environment) -> None:
        """Add globals and filters to the environment."""
        env.globals["insert_work_item"] = self.__insert_work_item
        env.globals["heading"] = self.__heading
        env.globals["work_item_field"] = self.__work_item_field
        env.filters["link_work_item"] = self.__link_work_item

    def __insert_work_item(
        self, obj: object, session: RenderingSession, level: int | None = None
    ) -> str:
        error_msg, proj_id, work_item = self._get_work_item(obj)

        if proj_id and work_item:
            assert work_item.id
            if (proj_id, work_item.id) in session.inserted_work_item_ids:
                logger.info(
                    "WorkItem %s is already in the document."
                    "A link will be added instead of inserting it.",
                    work_item.id,
                )
                return f"<p>{self.__link_work_item(obj)}</p>"

            assert work_item.type
            layout_index = polarion_html_helper.get_layout_index(
                "section", session.rendering_layouts, work_item.type
            )

            custom_info = ""
            if level is not None:
                custom_info = f"level={level}|"

            session.inserted_work_item_ids.append((proj_id, work_item.id))
            if proj_id != session.document_project_id:
                # pylint: disable-next=line-too-long
                return polarion_html_helper.POLARION_WORK_ITEM_DOCUMENT_PROJECT.format(
                    pid=work_item.id,
                    lid=layout_index,
                    custom_info=custom_info,
                    project=proj_id,
                )
            return polarion_html_helper.POLARION_WORK_ITEM_DOCUMENT.format(
                pid=work_item.id, lid=layout_index, custom_info=custom_info
            )

        logger.warning("Error inserting work item: %s", error_msg)
        return polarion_html_helper.RED_TEXT.format(
            text=f"Error inserting work item: {error_msg}"
        )

    def __link_work_item(self, obj: object) -> str:
        error_msg, proj_id, work_item = self._get_work_item(obj)

        if work_item and proj_id:
            return polarion_html_helper.POLARION_WORK_ITEM_URL_PROJECT.format(
                pid=work_item.id, project=proj_id
            )

        logger.warning("Error linking work item: %s", error_msg)
        return polarion_html_helper.RED_TEXT.format(
            text=f"Error linking work item: {error_msg}"
        )

    def _get_work_item(
        self, obj: object
    ) -> tuple[str, str | None, polarion_api.WorkItem | None]:
        if isinstance(obj, tuple) and len(obj) == PROJ_WI_PAIR_LEN:
            proj_id, work_item = obj
            if isinstance(proj_id, str) and isinstance(
                work_item, polarion_api.WorkItem
            ):
                return "", proj_id, work_item

        if (obj := self.check_model_element(obj)) is None:
            return "A non-model object was passed.", None, None

        if wi := self.polarion_repository.get_work_item_by_capella_uuid(
            obj.uuid
        ):
            return "", self.model_work_item_project_id, wi

        return (
            f"Missing WorkItem for {obj.xtype} {obj.name} ({obj.uuid})",
            None,
            None,
        )

    def __heading(
        self, level: int, text: str, session: RenderingSession
    ) -> str:
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
        polarion_type: str | None = None,
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
        polarion_type: str | None = None,
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
            polarion_type = document.type

        if polarion_name is None or polarion_folder is None:
            raise AssertionError(
                "You either need to pass a folder and a name or a document"
                " with a module_folder and a module_name defined"
            )

        env = self._get_jinja_env(template_folder)
        template = env.get_template(template_name)

        session = RenderingSession(
            document_project_id=document_project_id
            or self.model_work_item_project_id
        )
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
                type=polarion_type,
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
        document.type = None
        text_work_item_provider = (
            text_work_item_provider or twi.TextWorkItemProvider()
        )
        assert document.home_page_content, (
            "In mixed authority the document must have content"
        )
        assert document.home_page_content.value, (
            "In mixed authority the document must have content"
        )
        html_elements = lxmlhtml.fragments_fromstring(
            document.home_page_content.value
        )

        session = RenderingSession(
            rendering_layouts=document.rendering_layouts or [],
            document_project_id=document_project_id
            or self.model_work_item_project_id,
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
                    if not isinstance(element, str)
                ]
            ),
        )
        document.rendering_layouts = session.rendering_layouts

        return data_model.DocumentData(
            document, session.headings, text_work_item_provider
        )

    def _extract_section_areas(
        self,
        html_elements: list[lxmlhtml.HtmlElement | str],
        session: RenderingSession,
    ) -> dict[str, tuple[int, int]]:
        section_areas = {}
        current_area_id = None
        current_area_start = None
        for element_index, element in enumerate(html_elements):
            assert not isinstance(element, str)
            if (
                current_area_id is None
                and element.tag == "div"
                and (
                    wid_match := polarion_html_helper.WI_ID_REGEX.match(
                        element.get("id", "")
                    )
                )
            ):
                proj_id = (
                    session.document_project_id
                    or self.model_work_item_project_id
                )
                if proj_match := polarion_html_helper.WI_PROJECT_REGEX.match(
                    element.get("id", "")
                ):
                    proj_id = proj_match.group(1)
                session.inserted_work_item_ids.append(
                    (proj_id, wid_match.group(1))
                )
                continue

            if (
                element.tag != "div"
                or element.get("class") != "polarion-dle-wiki-block"
            ):
                continue
            for child in element.iterchildren():
                if child.get("class") == "polarion-dle-wiki-block-source":
                    text = html.unescape(child.text or "")
                    content = lxmlhtml.fragments_fromstring(text)
                    if (
                        content
                        and not isinstance(content[0], str)
                        and content[0].tag == "div"
                    ):
                        element_id = content[0].get("id")
                        if content[0].get("class") == AREA_START_CLS:
                            assert element_id is not None, (
                                "There was no id set to identify the area"
                            )
                            assert current_area_id is None, (
                                f"Started a new area {element_id} "
                                f"while being in area {current_area_id}"
                            )
                            current_area_id = element_id
                            current_area_start = element_index
                        elif content[0].get("class") == AREA_END_CLS:
                            assert element_id is not None, (
                                "There was no id set to identify the area"
                            )
                            assert current_area_id == element_id, (
                                f"Ended area {element_id} "
                                f"while being in area {current_area_id}"
                            )
                            assert current_area_start is not None
                            section_areas[current_area_id] = (
                                current_area_start,
                                element_index,
                            )
                            current_area_id = None
                            current_area_start = None
        return section_areas
