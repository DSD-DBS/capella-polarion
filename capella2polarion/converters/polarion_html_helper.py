# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Functions for polarion specific HTMl elements."""
from __future__ import annotations

import pathlib
import re

import capellambse
import jinja2
from capellambse import helpers as chelpers
from lxml import etree, html

heading_id_prefix = "polarion_wiki macro name=module-workitem;params=id="
h_regex = re.compile("h[0-9]")
wi_regex = re.compile(f"{heading_id_prefix}(.*)")


POLARION_WORK_ITEM_URL = (
    '<span class="polarion-rte-link" data-type="workItem" '
    'id="fake" data-item-id="{pid}" data-option-id="long">'
    "</span>"
)
POLARION_WORK_ITEM_DOCUMENT = (
    '<div id="polarion_wiki macro name=module-workitem;'
    'params=id={pid}|layout={lid}|{custom_info}external=true"></div>'
)
RE_DESCR_DELETED_PATTERN = re.compile(
    f"&lt;deleted element ({chelpers.RE_VALID_UUID.pattern})&gt;"
)
RED_TEXT = '<p style="color:red">{text}</p>'


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
    ) -> (
        capellambse.model.GenericElement
        | capellambse.model.diagram.AbstractDiagram
        | None
    ):
        """Check if a model element was passed.

        Return None if no element and raise a TypeError if a wrong typed
        element was passed. Returns the element if it matches
        expectations.
        """
        if jinja2.is_undefined(obj) or obj is None:
            return None

        if isinstance(obj, capellambse.model.ElementList):
            raise TypeError("Cannot make an href to a list of elements")
        if not isinstance(
            obj,
            (
                capellambse.model.GenericElement,
                capellambse.model.diagram.AbstractDiagram,
            ),
        ):
            raise TypeError(f"Expected a model object, got {obj!r}")
        return obj

    def setup_env(self, env: jinja2.Environment):
        """Implement this method to adjust a newly created environment."""


def remove_table_ids(
    html_content: str | list[etree._Element],
) -> list[etree._Element]:
    """Remove the ID field from all tables.

    This is necessary due to a bug in Polarion where Polarion does not
    ensure that the tables added in the UI have unique IDs. At the same
    time the REST-API does not allow posting or patching a document with
    multiple tables having the same ID.
    """
    html_fragments = _ensure_fragments(html_content)

    for element in html_fragments:
        if element.tag == "table":
            element.remove("id")

    return html_fragments


def _ensure_fragments(
    html_content: str | list[etree._Element],
) -> list[etree._Element]:
    if isinstance(html_content, str):
        return html.fragments_fromstring(html_content)
    return html_content


def extract_headings(html_content: str | list[etree._Element]) -> list[str]:
    """Return a list of work item IDs for all headings in the given content."""
    heading_ids = []
    html_fragments = _ensure_fragments(html_content)

    for element in html_fragments:
        if h_regex.fullmatch(element.tag):
            if matches := wi_regex.match(element.get("id")):
                heading_ids.append(matches.group(1))

    return heading_ids
