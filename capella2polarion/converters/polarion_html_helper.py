# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Functions for polarion specific HTMl elements."""
from __future__ import annotations

import pathlib
import re

import jinja2
import polarion_rest_api_client as polarion_api
from capellambse import helpers as chelpers
from capellambse import model as m
from lxml import html

WI_ID_PREFIX = "polarion_wiki macro name=module-workitem;params=id="
H_REGEX = re.compile("h[0-9]")
WI_ID_REGEX = re.compile(f"{WI_ID_PREFIX}([A-Z|a-z|0-9]*-[0-9]+)")

TEXT_WORK_ITEM_ID_FIELD = "__C2P__id"
TEXT_WORK_ITEM_TYPE = "text"
POLARION_WORK_ITEM_URL = (
    '<span class="polarion-rte-link" data-type="workItem" '
    'id="fake" data-item-id="{pid}" data-option-id="long">'
    "</span>"
)
POLARION_WORK_ITEM_URL_PROJECT = (
    '<span class="polarion-rte-link" data-type="workItem" '
    'id="fake" data-scope="{project}" data-item-id="{pid}" '
    'data-option-id="long"></span>'
)
POLARION_WORK_ITEM_DOCUMENT = (
    '<div id="polarion_wiki macro name=module-workitem;'
    'params=id={pid}|layout={lid}|{custom_info}external=true"></div>'
)
POLARION_WORK_ITEM_DOCUMENT_PROJECT = (
    '<div id="polarion_wiki macro name=module-workitem;'
    "params=id={pid}|layout={lid}|{custom_info}external=true"
    '|project={project}"></div>'
)
RE_DESCR_DELETED_PATTERN = re.compile(
    f"&lt;deleted element ({chelpers.RE_VALID_UUID.pattern})&gt;"
)
RED_TEXT = '<p style="color:red">{text}</p>'
WORK_ITEM_TAG = "workitem"


def strike_through(string: str) -> str:
    """Return a striked-through html span from given ``string``."""
    if match := RE_DESCR_DELETED_PATTERN.match(string):
        string = match.group(1)
    return f'<span style="text-decoration: line-through;">{string}</span>'


def generate_image_html(
    title: str, attachment_id: str, max_width: int, cls: str
) -> str:
    """Generate an image as HTMl with the given source."""
    description = (
        f'<span><img title="{title}" class="{cls}" '
        f'src="workitemimg:{attachment_id}" '
        f'style="max-width: {max_width}px;"/></span>'
    )
    return description


def camel_case_to_words(camel_case_str: str):
    """Split camel or dromedary case and return it as a space separated str."""
    return (
        camel_case_str[0].capitalize()
        + " ".join(
            re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", camel_case_str)
        )[1:]
    )


class JinjaRendererMixin:
    """A MixIn for converters which should render jinja frequently."""

    jinja_envs: dict[str, jinja2.Environment]

    def _get_jinja_env(self, template_folder: str | pathlib.Path):
        template_folder = str(template_folder)
        if env := self.jinja_envs.get(template_folder):
            return env

        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_folder)
        )
        self.setup_env(env)

        self.jinja_envs[template_folder] = env
        return env

    def check_model_element(
        self, obj: object
    ) -> m.ModelElement | m.AbstractDiagram | None:
        """Check if a model element was passed.

        Return None if no element and raise a TypeError if a wrong typed
        element was passed. Returns the element if it matches
        expectations.
        """
        if jinja2.is_undefined(obj) or obj is None:
            return None

        if isinstance(obj, m.ElementList):
            raise TypeError("Cannot make an href to a list of elements")
        if not isinstance(obj, (m.ModelElement, m.AbstractDiagram)):
            raise TypeError(f"Expected a model object, got {obj!r}")
        return obj

    def setup_env(self, env: jinja2.Environment):
        """Implement this method to adjust a newly created environment."""


def remove_table_ids(
    html_content: str | list[html.HtmlElement | str],
) -> list[html.HtmlElement | str]:
    """Remove the ID field from all tables.

    This is necessary due to a bug in Polarion where Polarion does not
    ensure that the tables added in the UI have unique IDs. At the same
    time the REST-API does not allow posting or patching a document with
    multiple tables having the same ID.
    """
    html_fragments = ensure_fragments(html_content)

    for element in html_fragments:
        if not isinstance(element, html.HtmlElement):
            continue

        if element.tag == "table":
            element.attrib.pop("id", None)

    return html_fragments


def ensure_fragments(
    html_content: str | list[html.HtmlElement | str],
) -> list[html.HtmlElement | str]:
    """Convert string to html elements."""
    if isinstance(html_content, str):
        return html.fragments_fromstring(html_content)
    return html_content


def extract_headings(
    html_content: str | list[html.HtmlElement | str],
) -> list[str]:
    """Return a list of work item IDs for all headings in the given content."""
    return extract_work_items(html_content, H_REGEX)


def extract_work_items(
    html_content: str | list[html.HtmlElement | str],
    tag_regex: re.Pattern | None = None,
) -> list[str]:
    """Return a list of work item IDs for work items in the given content."""
    work_item_ids: list[str] = []
    html_fragments = ensure_fragments(html_content)
    for element in html_fragments:
        if not isinstance(element, html.HtmlElement):
            continue

        if (tag_regex is not None and tag_regex.fullmatch(element.tag)) or (
            tag_regex is None and element.tag == "div"
        ):
            if matches := WI_ID_REGEX.match(element.get("id")):
                work_item_ids.append(matches.group(1))
    return work_item_ids


def get_layout_index(
    default_layouter: str,
    rendering_layouts: list[polarion_api.RenderingLayout],
    work_item_type: str,
) -> int:
    """Return the index of the layout of the requested workitem.

    If there is no rendering config yet, it will be created.
    """
    layout_index = 0
    for layout in rendering_layouts:
        if layout.type == work_item_type:
            return layout_index
        layout_index += 1
    if layout_index >= len(rendering_layouts):
        rendering_layouts.append(
            polarion_api.RenderingLayout(
                type=work_item_type,
                layouter=default_layouter,
                label=camel_case_to_words(work_item_type),
            )
        )
    return layout_index
