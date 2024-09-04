# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Provides a class to generate and inset text work items in documents."""
import polarion_rest_api_client as polarion_api
from lxml import html

from capella2polarion.converters import polarion_html_helper as html_helper


class TextWorkItemProvider:
    """Class providing text work items, their generation and insertion."""

    def __init__(
        self,
        text_work_item_id_field: str = html_helper.TEXT_WORK_ITEM_ID_FIELD,
        text_work_item_type: str = html_helper.TEXT_WORK_ITEM_TYPE,
        existing_text_work_items: list[polarion_api.WorkItem] | None = None,
    ):
        self.old_text_work_items: dict[str, polarion_api.WorkItem] = {}
        for work_item in existing_text_work_items or []:
            # We only use those work items which have an ID defined by us
            if text_id := work_item.additional_attributes.get(
                text_work_item_id_field
            ):
                if text_id in self.old_text_work_items:
                    raise ValueError(
                        f"There are multiple text work items with "
                        f"{text_work_item_id_field} == {text_id}"
                    )

                self.old_text_work_items[text_id] = work_item

        self.text_work_item_id_field = text_work_item_id_field
        self.text_work_item_type = text_work_item_type
        self.new_text_work_items: dict[str, polarion_api.WorkItem] = {}

    def generate_text_work_items(
        self,
        content: list[html.HtmlElement] | str,
        work_item_id_filter: list[str] | None = None,
    ):
        """Generate text work items from the provided html."""
        content = html_helper.ensure_fragments(content)
        for element in content:
            if element.tag != html_helper.WORK_ITEM_TAG:
                continue

            if not (text_id := element.get("id")):
                raise ValueError("All work items must have an ID in template")

            if not (
                (work_item := self.old_text_work_items.get(text_id))
                and (
                    work_item_id_filter is None
                    or work_item.id in work_item_id_filter
                )
            ):
                work_item = polarion_api.WorkItem(
                    type=self.text_work_item_type,
                    title="",
                    status="open",
                    additional_attributes={
                        self.text_work_item_id_field: text_id
                    },
                )

            work_item.description_type = "text/html"
            inner_content = "".join(
                [
                    (
                        html.tostring(child, encoding="unicode")
                        if isinstance(child, html.HtmlElement)
                        else child
                    )
                    for child in element.iterchildren()
                ]
            )
            if element.text:
                inner_content = element.text + inner_content

            work_item.description = inner_content
            self.new_text_work_items[text_id] = work_item

    def insert_text_work_items(
        self,
        document: polarion_api.Document,
    ):
        """Insert text work items into the given document."""
        if not self.new_text_work_items:
            return

        assert document.home_page_content is not None
        assert document.rendering_layouts is not None
        layout_index = html_helper.get_layout_index(
            "paragraph", document.rendering_layouts, self.text_work_item_type
        )
        html_fragments = html_helper.ensure_fragments(
            document.home_page_content.value
        )
        new_content = []
        last_match = -1
        for index, element in enumerate(html_fragments):
            if not isinstance(element, html.HtmlElement):
                continue

            if element.tag == "workitem":
                new_content += html_fragments[last_match + 1 : index]
                last_match = index
                if work_item := self.new_text_work_items.get(
                    element.get("id")
                ):
                    new_content.append(
                        html.fromstring(
                            html_helper.POLARION_WORK_ITEM_DOCUMENT.format(
                                pid=work_item.id,
                                lid=layout_index,
                                custom_info="",
                            )
                        )
                    )

        new_content += html_fragments[last_match + 1 :]
        document.home_page_content.value = "\n".join(
            [html.tostring(element).decode("utf-8") for element in new_content]
        )
