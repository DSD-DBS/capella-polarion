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

from . import polarion_html_helper

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
    inserted_work_items: list[polarion_api.WorkItem] = dataclasses.field(
        default_factory=list
    )


class DocumentRenderer(polarion_html_helper.JinjaRendererMixin):
    """A Renderer class for Polarion documents."""

    def __init__(
        self,
        polarion_repository: polarion_repo.PolarionDataRepository,
        model: capellambse.MelodyModel,
    ):
        self.polarion_repository = polarion_repository
        self.model = model
        self.jinja_envs: dict[str, jinja2.Environment] = {}

    def setup_env(self, env: jinja2.Environment):
        """Add globals and filters to the environment."""
        env.globals["insert_work_item"] = self.__insert_work_item
        env.globals["heading"] = self.__heading
        env.globals["work_item_field"] = self.__work_item_field
        env.filters["link_work_item"] = self.__link_work_item

    def __insert_work_item(
        self, obj: object, session: RenderingSession, level: int | None = None
    ) -> str:
        if (obj := self.check_model_element(obj)) is None:
            return polarion_html_helper.RED_TEXT.format(
                text="A none model object was passed to insert a work item."
            )

        if wi := self.polarion_repository.get_work_item_by_capella_uuid(
            obj.uuid
        ):
            if wi in session.inserted_work_items:
                logger.info(
                    "WorkItem %s is already in the document."
                    "A link will be added instead of inserting it.",
                    wi.id,
                )
                return f"<p>{self.__link_work_item(obj)}</p>"

            layout_index = 0
            for layout in session.rendering_layouts:
                if layout.type == wi.type:
                    break
                layout_index += 1

            if layout_index >= len(session.rendering_layouts):
                session.rendering_layouts.append(
                    polarion_api.RenderingLayout(
                        type=wi.type,
                        layouter="section",
                        label=polarion_html_helper.camel_case_to_words(
                            wi.type
                        ),
                    )
                )

            custom_info = ""
            if level is not None:
                custom_info = f"level={level}|"

            session.inserted_work_items.append(wi)

            return polarion_html_helper.POLARION_WORK_ITEM_DOCUMENT.format(
                pid=wi.id, lid=layout_index, custom_info=custom_info
            )

        return polarion_html_helper.RED_TEXT.format(
            text=f"Missing WorkItem for UUID {obj.uuid}"
        )

    def __link_work_item(self, obj: object) -> str:
        if (obj := self.check_model_element(obj)) is None:
            raise TypeError("object passed was no model element")

        if wi := self.polarion_repository.get_work_item_by_capella_uuid(
            obj.uuid
        ):
            return polarion_html_helper.POLARION_WORK_ITEM_URL.format(
                pid=wi.id
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
                f'id="{polarion_html_helper.heading_id_prefix}{hid}">'
                f"</h{level}>"
            )
        return f"<h{level}>{text}</h{level}>"

    def __work_item_field(self, obj: object, field: str) -> t.Any:
        if (obj := self.check_model_element(obj)) is None:
            raise TypeError("object passed was no model element")

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
        **kwargs: t.Any,
    ):
        """Render a new Polarion document."""

    @t.overload
    def render_document(
        self,
        template_folder: str | pathlib.Path,
        template_name: str,
        *,
        document: polarion_api.Document,
        **kwargs: t.Any,
    ):
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
        **kwargs: t.Any,
    ):
        """Render a Polarion document."""
        if document is not None:
            polarion_folder = document.module_folder
            polarion_name = document.module_name

        assert polarion_name is not None and polarion_folder is not None, (
            "You either need to pass a folder and a name or a document with a "
            "module_folder and a module_name defined"
        )

        env = self._get_jinja_env(template_folder)
        template = env.get_template(template_name)

        session = RenderingSession()
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

        document.home_page_content = polarion_api.TextContent(
            "text/html",
            template.render(model=self.model, session=session, **kwargs),
        )
        document.rendering_layouts = session.rendering_layouts

        return document, session.headings

    def update_mixed_authority_document(
        self,
        document: polarion_api.Document,
        template_folder: str | pathlib.Path,
        sections: dict[str, str],
        global_parameters: dict[str, t.Any],
        section_parameters: dict[str, dict[str, t.Any]],
    ):
        """Update a mixed authority document."""
        assert (
            document.home_page_content and document.home_page_content.value
        ), "In mixed authority the document must have content"
        html_elements = lxmlhtml.fragments_fromstring(
            document.home_page_content.value
        )
        section_areas = self._extract_section_areas(html_elements)

        session = RenderingSession(
            rendering_layouts=document.rendering_layouts
        )
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
            new_content += lxmlhtml.fragments_fromstring(content)

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

        return document, session.headings

    def _extract_section_areas(self, html_elements: list[etree._Element]):
        section_areas = {}
        current_area_id = None
        current_area_start = None
        for element_index, element in enumerate(html_elements):
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
                        if content[0].get("class") == "c2pAreaStart":
                            assert (
                                element_id is not None
                            ), "There was no id set to identify the area"
                            assert current_area_id is None, (
                                f"Started a new area {element_id} "
                                f"while being in area {current_area_id}"
                            )
                            current_area_id = element_id
                            current_area_start = element_index
                        elif content[0].get("class") == "c2pAreaEnd":
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
