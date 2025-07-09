# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Provides Capella object specific rendering functionalities."""

from __future__ import annotations

import collections
import hashlib
import mimetypes
import pathlib
import re
import typing as t

import capellambse
import datauri
import jinja2
import markupsafe
import polarion_rest_api_client as polarion_api
from capellambse import helpers as chelpers
from capellambse import model as m
from capellambse_context_diagrams import context
from lxml import etree, html

from capella2polarion import data_model, polarion_html_helper
from capella2polarion.connectors import polarion_repo
from capella2polarion.elements import data_session

RE_DESCR_LINK_PATTERN = re.compile(
    r"<a href=\"hlink://([^\"]+)\">([^<]+)<\/a>"
)
C2P_IMAGE_PREFIX = "__C2P__"
JINJA_RENDERED_IMG_CLS = "jinja-rendered-image"


class CapellaObjectRenderer(polarion_html_helper.JinjaRendererMixin):
    """A class for work item generating plugins and generators."""

    def __init__(
        self,
        model: capellambse.MelodyModel,
        generate_figure_captions: bool,
        generate_attachments: bool,
        capella_polarion_mapping: polarion_repo.PolarionDataRepository,
    ):
        self.model = model
        self.generate_figure_captions = generate_figure_captions
        self.generate_attachments = generate_attachments
        self.capella_polarion_mapping = capella_polarion_mapping
        self.jinja_envs: dict[str, jinja2.Environment] = {}

        self._attachment_creators: dict[
            type[m.AbstractDiagram], type[data_model.CapellaDiagramAttachment]
        ] = {
            context.ContextDiagram: data_model.CapellaContextDiagramAttachment,
        }

    def sanitize_text(
        self,
        obj: m.ModelElement | m.Diagram,
        text: markupsafe.Markup | str,
        errors: set[str],
    ) -> tuple[
        list[str],
        markupsafe.Markup,
        list[data_model.Capella2PolarionAttachment],
    ]:
        """Convert Capella texts to Polarion HTML with links and images."""
        referenced_uuids: list[str] = []
        replaced_markup = RE_DESCR_LINK_PATTERN.sub(
            lambda match: self.replace_markup(
                match, referenced_uuids, errors, 2
            ),
            text,
        )

        attachments: list[data_model.Capella2PolarionAttachment] = []

        def repair_images(node: etree._Element) -> None:
            if (
                node.tag != "img"
                or not self.generate_attachments
                or node.get("class") == JINJA_RENDERED_IMG_CLS
            ):
                return

            if not node.get("src", "").startswith("data:"):
                return
            data_uri = datauri.DataURI(node.get("src", ""))
            mime_type = data_uri.mimetype
            assert mime_type is not None, "Unknown mime type"
            if data_path := node.attrib.pop("data-capella-path", None):
                file_path = pathlib.Path(data_path)
                title = file_path.stem
                file_name = file_path.name
            else:
                try:
                    title = hashlib.md5(data_uri.data).hexdigest()
                    suffix = mimetypes.guess_extension(mime_type)
                    assert suffix is not None, "Unknown file suffix"
                    file_name = title + suffix
                except (ValueError, AssertionError) as e:
                    errors.add(
                        f"Inline image can't be loaded {data_uri[:8]!r}: {e}"
                    )
                    return

            attachments.append(
                data_model.Capella2PolarionAttachment(
                    "",
                    "",
                    title,
                    data_uri.data,
                    mime_type,
                    file_name,
                )
            )

            # We use the filename here as the ID is unknown here
            # This needs to be refactored after updating attachments
            node.attrib["src"] = f"workitemimg:{file_name}"
            if self.generate_figure_captions:
                caption = node.get("alt", f'Image "{title}" of {obj.name}')
                node.addnext(
                    html.fromstring(
                        polarion_html_helper.POLARION_CAPTION.format(
                            label="Figure", caption=caption
                        )
                    )
                )

        repaired_markup = chelpers.process_html_fragments(
            replaced_markup, repair_images
        )
        return referenced_uuids, repaired_markup, attachments

    def replace_markup(
        self,
        match: re.Match,
        referenced_uuids: list[str],
        errors: set[str],
        default_group: int = 1,
    ) -> str:
        """Replace UUID references in a ``match`` with a work item link.

        If the UUID doesn't correspond to an existing work item the
        original text is returned.
        """
        uuid = match.group(1)
        try:
            self.model.by_uuid(uuid)
        except KeyError:
            errors.add(
                f"Non-existing model element referenced in description: {uuid}"
            )
            return polarion_html_helper.strike_through(
                match.group(default_group)
            )
        if pid := self.capella_polarion_mapping.get_work_item_id(uuid):
            referenced_uuids.append(uuid)
            return polarion_html_helper.POLARION_WORK_ITEM_URL.format(pid=pid)

        errors.add(f"Non-existing work item referenced in description: {uuid}")
        return match.group(default_group)

    def sanitize_linked_text(
        self,
        obj: m.ModelElement | m.Diagram,
        errors: set[str],
    ) -> tuple[
        list[str],
        markupsafe.Markup,
        list[data_model.Capella2PolarionAttachment],
    ]:
        """Get the linked text and return it sanitized."""
        linked_text = getattr(
            obj, "specification", {"capella:linkedText": markupsafe.Markup("")}
        )["capella:linkedText"]
        linked_text = polarion_html_helper.RE_DESCR_DELETED_PATTERN.sub(
            lambda match: polarion_html_helper.strike_through(
                self.replace_markup(match, [], errors)
            ),
            linked_text,
        )
        linked_text = linked_text.replace("\n", "<br>")
        return self.sanitize_text(obj, linked_text, errors)

    @staticmethod
    def get_requirement_types_text(
        obj: m.ModelElement | m.Diagram, errors: set[str]
    ) -> dict[str, polarion_api.HtmlContent]:
        """Get the requirement texts and return them."""
        type_texts = collections.defaultdict(list)
        for req in getattr(obj, "requirements", []):
            if req is None:
                errors.add("Found RequirementsRelation with broken target")
                continue

            if not (req.type and req.text):
                identifier = (
                    req.long_name or req.name or req.summary or req.uuid
                )
                errors.add(
                    f"Found Requirement without text or type on {identifier!r}"
                )
                continue

            type_texts[req.type.long_name].append(req.text)

        def _format(texts: list[str]) -> polarion_api.HtmlContent:
            if len(texts) > 1:
                items = "".join(f"<li>{text}</li>" for text in texts)
                text = f"<ul>{items}</ul>"
            else:
                text = texts[0]
            return polarion_api.HtmlContent(text)

        return {
            typ.lower(): _format(texts) for typ, texts in type_texts.items()
        }

    def render_jinja_template(
        self,
        template_folder: str | pathlib.Path,
        template_path: str | pathlib.Path,
        converter_data: data_session.ConverterData,
        render_params: dict[str, t.Any] | None = None,
    ) -> tuple[
        list[str],
        markupsafe.Markup,
        list[data_model.Capella2PolarionAttachment],
    ]:
        """Render jinja template for model element and return polarion text."""
        env = self._get_jinja_env(str(template_folder))
        template = env.get_template(str(template_path))
        rendered_jinja = template.render(
            object=converter_data.capella_element,
            model=self.model,
            work_item=converter_data.work_item,
            config=converter_data.type_config,
            **(render_params or {}),
        )
        return self.sanitize_text(
            converter_data.capella_element,
            rendered_jinja,
            converter_data.errors,
        )

    def setup_env(self, env: jinja2.Environment) -> None:
        """Add the link rendering filter."""
        env.filters["make_href"] = self.__make_href_filter
        env.globals["insert_diagram"] = self.__insert_diagram

    def __make_href_filter(self, obj: object) -> str:
        if (obj := self.check_model_element(obj)) is None:
            return "#"
        return f"hlink://{obj.uuid}"

    def __insert_diagram(
        self,
        work_item: polarion_api.WorkItem | None,
        diagram: m.AbstractDiagram,
        file_name: str,
        render_params: dict[str, t.Any] | None = None,
        max_width: int = 800,
        caption: tuple[str, str] | None = None,
    ) -> str:
        if work_item is None:
            raise ValueError("To render a diagram the work item must be set.")
        if attachment := next(
            (
                att
                for att in work_item.attachments
                if att.file_name == f"{C2P_IMAGE_PREFIX}{file_name}.svg"
            ),
            None,
        ):
            assert attachment.file_name is not None
            return polarion_html_helper.generate_image_html(
                diagram.name,
                attachment.file_name,
                max_width,
                JINJA_RENDERED_IMG_CLS,
                caption,
            )

        diagram_html, attachment = self.draw_diagram_svg(
            diagram,
            file_name,
            diagram.name,
            max_width,
            JINJA_RENDERED_IMG_CLS,
            render_params,
        )
        if attachment:
            polarion_html_helper.add_attachment_to_workitem(
                work_item, attachment
            )

        return diagram_html

    def _create_diagram_attachment(
        self,
        diagram: m.AbstractDiagram,
        file_name: str,
        render_params: dict[str, t.Any] | None,
        title: str,
    ) -> data_model.CapellaDiagramAttachment:
        attachment_class = self._attachment_creators.get(
            type(diagram), data_model.CapellaDiagramAttachment
        )
        return attachment_class(diagram, file_name, render_params, title)

    def draw_diagram_svg(
        self,
        diagram: m.AbstractDiagram,
        file_name: str,
        title: str,
        max_width: int,
        cls: str,
        render_params: dict[str, t.Any] | None = None,
        caption: str | None = None,
    ) -> tuple[str, data_model.CapellaDiagramAttachment | None]:
        """Return the provided diagram as attachment and HTML."""
        file_name = f"{C2P_IMAGE_PREFIX}{file_name}.svg"

        if self.generate_attachments:
            attachment = self._create_diagram_attachment(
                diagram, file_name, render_params, title
            )
        else:
            attachment = None

        return (
            polarion_html_helper.generate_image_html(
                title,
                file_name,
                max_width,
                cls,
                (
                    ("Figure", caption or f"Diagram {diagram.name}")
                    if self.generate_figure_captions
                    else None
                ),
            ),
            attachment,
        )
