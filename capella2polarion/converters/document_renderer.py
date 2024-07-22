# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""A jinja renderer for Polarion documents."""

import dataclasses
import pathlib
import re
import typing as t

import capellambse
import jinja2
import polarion_rest_api_client as polarion_api
from capellambse import helpers as chelpers
from lxml import etree

from capella2polarion.connectors import polarion_repo

from . import polarion_html_helper

heading_id_prefix = "polarion_wiki macro name=module-workitem;params=id="
h_regex = re.compile("h[0-9]")
wi_regex = re.compile(f"{heading_id_prefix}(.*)")


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
        env.filters["link_work_item"] = self.__link_work_item

    def __insert_work_item(
        self, obj: object, session: RenderingSession, level: int | None = None
    ) -> str | None:
        if (obj := self.check_model_element(obj)) is None:
            return polarion_html_helper.RED_TEXT.format(
                text="A none model object was passed to insert a work item."
            )

        if wi := self.polarion_repository.get_work_item_by_capella_uuid(
            obj.uuid
        ):
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

            return polarion_html_helper.POLARION_WORK_ITEM_DOCUMENT.format(
                pid=wi.id, lid=layout_index, custom_info=custom_info
            )

        return polarion_html_helper.RED_TEXT.format(
            text=f"Missing WorkItem for UUID {obj.uuid}"
        )

    def __link_work_item(self, obj: object) -> str | None:
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
            return f'<h{level} id="{heading_id_prefix}{hid}"></h{level}>'
        return f"<h{level}>{text}</h{level}>"

    @t.overload
    def render_document(
        self,
        template_folder: str | pathlib.Path,
        template_name: str,
        polarion_folder: str,
        polarion_name: str,
        document_title: str | None = None,
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
                session.heading_ids = self._extract_headings(document)
        else:
            document = polarion_api.Document(
                title=document_title,
                module_folder=polarion_folder,
                module_name=polarion_name,
            )

        document.home_page_content = polarion_api.TextContent(
            "text/html",
            template.render(model=self.model, session=session, **kwargs),
        )
        document.rendering_layouts = session.rendering_layouts

        return document, session.headings

    def _extract_headings(self, document):
        heading_ids = []

        def collect_heading_work_items(element: etree._Element):
            if h_regex.fullmatch(element.tag):
                matches = wi_regex.match(element.get("id"))
                if matches:
                    heading_ids.append(matches.group(1))

        chelpers.process_html_fragments(
            document.home_page_content.value, collect_heading_work_items
        )
        return heading_ids
