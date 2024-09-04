# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module for polarion API client work."""
from __future__ import annotations

import collections.abc as cabc
import json
import logging
import typing as t
from urllib import parse

import polarion_rest_api_client as polarion_api
from capellambse import helpers as chelpers
from lxml import etree

from capella2polarion import data_models
from capella2polarion.connectors import polarion_repo
from capella2polarion.converters import data_session

logger = logging.getLogger(__name__)


DEFAULT_ATTRIBUTE_VALUES: dict[type, t.Any] = {
    str: "",
    int: 0,
    bool: False,
}
WORK_ITEMS_IN_PROJECT_QUERY = (
    "SQL:(SELECT item.* FROM POLARION.WORKITEM item, POLARION.MODULE doc, "
    "POLARION.PROJECT proj WHERE proj.C_ID = '{project}' AND "
    "doc.FK_PROJECT = proj.C_PK AND doc.C_ID = '{doc_name}' AND "
    "doc.C_MODULEFOLDER = '{doc_folder}' AND item.C_TYPE = '{wi_type}' AND "
    "EXISTS (SELECT rel1.* FROM POLARION.REL_MODULE_WORKITEM rel1 WHERE "
    "rel1.FK_URI_MODULE = doc.C_URI AND rel1.FK_URI_WORKITEM = item.C_URI))"
)
"""An SQL query to get work items which are inserted in a given document."""


class PolarionWorkerParams:
    """Container for Polarion Params."""

    def __init__(
        self, project_id: str, url: str, pat: str, delete_work_items: bool
    ) -> None:
        self.project_id = project_id
        self.url = url
        self.private_access_token = pat
        self.delete_work_items = delete_work_items


class CapellaPolarionWorker:
    """CapellaPolarionWorker encapsulate the Polarion API Client work."""

    def __init__(
        self, params: PolarionWorkerParams, force_update: bool = False
    ) -> None:
        self.polarion_params = params
        self.polarion_data_repo = polarion_repo.PolarionDataRepository()
        self.force_update = force_update

        if (self.polarion_params.project_id is None) or (
            len(self.polarion_params.project_id) == 0
        ):
            raise ValueError(
                f"""ProjectId invalid. Value
                '{self.polarion_params.project_id}'"""
            )

        result_url = parse.urlparse(self.polarion_params.url)
        if not all([result_url.scheme, result_url.netloc]):
            raise ValueError(
                f"""Polarion URL parameter is not a valid url.
                Value {self.polarion_params.url}"""
            )
        if self.polarion_params.private_access_token is None:
            raise ValueError(
                "Polarion PAT (Personal Access Token) parameter "
                "is not a set properly."
            )

        self.polarion_client = polarion_api.PolarionClient(
            polarion_api_endpoint=f"{self.polarion_params.url}/rest/v1",
            polarion_access_token=self.polarion_params.private_access_token,
        )
        self.project_client = self.polarion_client.generate_project_client(
            project_id=self.polarion_params.project_id,
            delete_status=(
                "deleted" if self.polarion_params.delete_work_items else None
            ),
            add_work_item_checksum=True,
        )
        self._additional_clients: dict[str, polarion_api.ProjectClient] = {}
        self.check_client()

    def _get_client(
        self, project_id: str | None
    ) -> polarion_api.ProjectClient:
        if project_id is None:
            return self.project_client
        if project_id in self._additional_clients:
            return self._additional_clients[project_id]
        client = self.polarion_client.generate_project_client(
            project_id=project_id,
            delete_status=(
                "deleted" if self.polarion_params.delete_work_items else None
            ),
            add_work_item_checksum=True,
        )
        if not client.exists():
            raise KeyError(f"Miss Polarion project with id {project_id}")
        self._additional_clients[project_id] = client
        return client

    def check_client(self) -> None:
        """Instantiate the polarion client as member."""
        if not self.project_client.exists():
            raise KeyError(
                "Miss Polarion project with id "
                f"{self.polarion_params.project_id}"
            )

    def load_polarion_work_item_map(self):
        """Return a map from Capella UUIDs to Polarion work items."""
        work_items = self.project_client.work_items.get_all(
            "HAS_VALUE:uuid_capella",
            fields={"workitems": "id,uuid_capella,checksum,status,type"},
            work_item_cls=data_models.CapellaWorkItem,
        )
        self.polarion_data_repo.update_work_items(work_items)

    def delete_orphaned_work_items(
        self, converter_session: data_session.ConverterSession
    ) -> None:
        """Delete work items in a Polarion project.

        If the delete flag is set to ``False`` in the context work items
        are marked as ``to be deleted`` via the status attribute.
        """

        existing_work_items = {
            uuid
            for uuid, _, work_item in self.polarion_data_repo.items()
            if work_item.status != "deleted"
        }
        uuids: set[str] = existing_work_items - set(converter_session)
        work_items: list[data_models.CapellaWorkItem] = []
        for uuid in uuids:
            if wi := self.polarion_data_repo.get_work_item_by_capella_uuid(
                uuid
            ):
                logger.info("Delete work item %r...", wi.id)
                work_items.append(wi)
            try:
                self.project_client.work_items.delete(work_items)
            except polarion_api.PolarionApiException as error:
                logger.error("Deleting work items failed. %s", error.args[0])
                raise error

        self.polarion_data_repo.remove_work_items_by_capella_uuid(uuids)

    def create_missing_work_items(
        self, converter_session: data_session.ConverterSession
    ) -> None:
        """Post work items in a Polarion project."""
        missing_work_items: list[data_models.CapellaWorkItem] = []
        for uuid, converter_data in converter_session.items():
            if not (work_item := converter_data.work_item):
                logger.warning(
                    "Expected to find a WorkItem for %s, but there is none",
                    uuid,
                )
                continue

            assert work_item is not None
            if work_item.uuid_capella in self.polarion_data_repo:
                continue

            missing_work_items.append(work_item)
            logger.info("Create work item for %r...", work_item.title)
        if missing_work_items:
            try:
                self.project_client.work_items.create(missing_work_items)
                self.polarion_data_repo.update_work_items(missing_work_items)
            except polarion_api.PolarionApiException as error:
                logger.error("Creating work items failed. %s", error.args[0])
                raise error

    def compare_and_update_work_item(
        self, converter_data: data_session.ConverterData
    ):
        """Patch a given WorkItem."""
        new = converter_data.work_item
        assert new is not None
        uuid = new.uuid_capella
        _, old = self.polarion_data_repo[uuid]
        assert old is not None

        new.calculate_checksum()
        if not self.force_update and new == old:
            return

        log_args = (old.id, new.type, new.title)
        logger.info(
            "Update work item %r for model element %s %r...", *log_args
        )

        if old.get_current_checksum()[0] != "{":  # XXX: Remove in next release
            old_checksums = {"__C2P__WORK_ITEM": old.get_current_checksum()}
        else:
            old_checksums = json.loads(old.get_current_checksum())

        new_checksums = json.loads(new.get_current_checksum())

        new_work_item_check_sum = new_checksums.pop("__C2P__WORK_ITEM")
        old_work_item_check_sum = old_checksums.pop("__C2P__WORK_ITEM")

        work_item_changed = new_work_item_check_sum != old_work_item_check_sum
        try:
            if work_item_changed or self.force_update:
                old = self.project_client.work_items.get(
                    old.id, work_item_cls=data_models.CapellaWorkItem
                )
                if old.attachments:
                    old_attachments = (
                        self.project_client.work_items.attachments.get_all(
                            work_item_id=old.id
                        )
                    )
                else:
                    old_attachments = []
            else:
                old_attachments = (
                    self.project_client.work_items.attachments.get_all(
                        work_item_id=old.id
                    )
                )
            if old_attachments or new.attachments:
                work_item_changed |= self.update_attachments(
                    new, old_checksums, new_checksums, old_attachments
                )
        except polarion_api.PolarionApiException as error:
            logger.error(
                "Updating attachments for WorkItem %r (%s %s) failed. %s",
                *log_args,
                error.args[0],
            )
            raise error

        assert new.id is not None
        delete_links = None
        create_links = None

        if work_item_changed or self.force_update:
            if new.attachments:
                self._refactor_attached_images(new)

            del new.additional_attributes["uuid_capella"]
            del old.additional_attributes["uuid_capella"]

            if old.linked_work_items_truncated:
                old.linked_work_items = (
                    self.project_client.work_items.links.get_all(old.id)
                )

            # Type will only be updated, if set and should be used carefully
            if new.type == old.type:
                new.type = None
            new.status = "open"

            # If additional fields were present, but aren't anymore,
            # we have to set them to an empty value manually
            defaults = DEFAULT_ATTRIBUTE_VALUES
            for attribute, value in old.additional_attributes.items():
                if attribute not in new.additional_attributes:
                    new.additional_attributes[attribute] = defaults.get(
                        type(value)
                    )
                elif new.additional_attributes[attribute] == value:
                    del new.additional_attributes[attribute]

            delete_links = CapellaPolarionWorker.get_missing_link_ids(
                old.linked_work_items, new.linked_work_items
            )
            create_links = CapellaPolarionWorker.get_missing_link_ids(
                new.linked_work_items, old.linked_work_items
            )
        else:
            new.additional_attributes = {}
            new.type = None
            new.status = None
            new.description = None
            new.description_type = None
            new.title = None

        try:
            self.project_client.work_items.update(new)
            if delete_links:
                id_list_str = ", ".join(delete_links.keys())
                logger.info(
                    "Delete work item links %r for model %s %r",
                    id_list_str,
                    new.type,
                    new.title,
                )
                self.project_client.work_items.links.delete(
                    list(delete_links.values())
                )

            if create_links:
                id_list_str = ", ".join(create_links.keys())
                logger.info(
                    "Create work item links %r for model %s %r",
                    id_list_str,
                    new.type,
                    new.title,
                )
                self.project_client.work_items.links.create(
                    list(create_links.values())
                )

        except polarion_api.PolarionApiException as error:
            logger.error(
                "Updating work item %r (%s %s) failed. %s",
                *log_args,
                error.args[0],
            )
            raise error

    def _refactor_attached_images(self, new: data_models.CapellaWorkItem):
        def set_attachment_id(node: etree._Element) -> None:
            if node.tag != "img":
                return
            if img_src := node.attrib.get("src"):
                if img_src.startswith("workitemimg:"):
                    file_name = img_src[12:]
                    for attachment in new.attachments:
                        if attachment.file_name == file_name:
                            node.attrib["src"] = f"workitemimg:{attachment.id}"
                            return

                    logger.error(
                        "Did not find attachment ID for file name %s",
                        file_name,
                    )

        if new.description:
            new.description = chelpers.process_html_fragments(
                new.description, set_attachment_id
            )
        for _, attributes in new.additional_attributes.items():
            if (
                isinstance(attributes, dict)
                and attributes.get("type") == "text/html"
                and attributes.get("value") is not None
            ):
                attributes["value"] = chelpers.process_html_fragments(
                    attributes["value"], set_attachment_id
                )

    def update_attachments(
        self,
        new: data_models.CapellaWorkItem,
        old_checksums: dict[str, str],
        new_checksums: dict[str, str],
        old_attachments: list[polarion_api.WorkItemAttachment],
    ) -> bool:
        """Delete, create and update attachments in one go.

        Returns True if new attachments were created. After execution
        all attachments of the new work item should have IDs.
        """
        new_attachment_dict = {
            attachment.file_name: attachment for attachment in new.attachments
        }
        old_attachment_dict = {
            attachment.file_name: attachment for attachment in old_attachments
        }

        created = False

        for attachment in old_attachments:
            if attachment not in old_attachment_dict.values():
                logger.error(
                    "There are already multiple attachments named %s. "
                    "Attachment with ID %s will be deleted for that reason"
                    " - please report this as issue.",
                    attachment.file_name,
                    attachment.id,
                )
                self.project_client.work_items.attachments.delete(attachment)

        old_attachment_file_names = set(old_attachment_dict)
        new_attachment_file_names = set(new_attachment_dict)
        for file_name in old_attachment_file_names - new_attachment_file_names:
            self.project_client.work_items.attachments.delete(
                old_attachment_dict[file_name]
            )

        if new_attachments := list(
            map(
                new_attachment_dict.get,
                new_attachment_file_names - old_attachment_file_names,
            )
        ):
            self.project_client.work_items.attachments.create(new_attachments)
            created = True

        attachments_for_update = {}
        for common_attachment_file_name in (
            old_attachment_file_names & new_attachment_file_names
        ):
            attachment = new_attachment_dict[common_attachment_file_name]
            attachment.id = old_attachment_dict[common_attachment_file_name].id
            if (
                new_checksums.get(attachment.file_name)
                != old_checksums.get(attachment.file_name)
                or self.force_update
                or attachment.mime_type == "image/svg+xml"
            ):
                attachments_for_update[attachment.file_name] = attachment

        for file_name, attachment in attachments_for_update.items():
            # SVGs should only be updated if their PNG differs
            if (
                attachment.mime_type == "image/svg+xml"
                and file_name[:-3] + "png" not in attachments_for_update
            ):
                continue

            self.project_client.work_items.attachments.update(attachment)
        return created

    @staticmethod
    def get_missing_link_ids(
        left: cabc.Iterable[polarion_api.WorkItemLink],
        right: cabc.Iterable[polarion_api.WorkItemLink],
    ) -> dict[str, polarion_api.WorkItemLink]:
        """Return an ID-Link dict of links present in left and not in right."""
        left_id_map = {
            CapellaPolarionWorker._get_link_id(link): link for link in left
        }
        right_id_map = {
            CapellaPolarionWorker._get_link_id(link): link for link in right
        }
        return {
            lid: left_id_map[lid]
            for lid in set(left_id_map) - set(right_id_map)
        }

    @staticmethod
    def _get_link_id(link: polarion_api.WorkItemLink) -> str:
        return "/".join(
            (
                link.primary_work_item_id,
                link.role,
                link.secondary_work_item_project,
                link.secondary_work_item_id,
            )
        )

    def compare_and_update_work_items(
        self, converter_session: data_session.ConverterSession
    ) -> None:
        """Update work items in a Polarion project."""
        for uuid, data in converter_session.items():
            if uuid in self.polarion_data_repo and data.work_item is not None:
                self.compare_and_update_work_item(data)

    def create_documents(
        self,
        document_datas: list[data_models.DocumentData],
        document_project: str | None = None,
    ):
        """Create new documents.

        Notes
        -----
        If the ``document_project`` is ``None`` the default client is
        taken.
        """
        client = self._get_client(document_project)
        documents, _ = self._process_document_datas(client, document_datas)

        client.documents.create(documents)

    def update_documents(
        self,
        document_datas: list[data_models.DocumentData],
        document_project: str | None = None,
    ):
        """Update existing documents.

        Notes
        -----
        If the ``document_project`` is ``None`` the default client is
        taken.
        """
        client = self._get_client(document_project)
        documents, headings = self._process_document_datas(
            client, document_datas
        )

        client.work_items.update(headings)
        client.documents.update(documents)

    def _process_document_datas(
        self,
        client: polarion_api.ProjectClient,
        document_datas: list[data_models.DocumentData],
    ):
        documents: list[polarion_api.Document] = []
        headings: list[polarion_api.WorkItem] = []
        for document_data in document_datas:
            headings.extend(document_data.headings)
            documents.append(document_data.document)
            if document_data.text_work_item_provider.new_text_work_items:
                self._create_and_update_text_work_items(
                    document_data.text_work_item_provider.new_text_work_items,
                    client,
                )
                document_data.text_work_item_provider.insert_text_work_items(
                    document_data.document,
                )
        return documents, headings

    def get_document(
        self, space: str, name: str, document_project: str | None = None
    ) -> polarion_api.Document | None:
        """Get a document from polarion and return None if not found.

        Notes
        -----
        If the ``document_project`` is ``None`` the default client is
        taken.
        """
        client = self._get_client(document_project)
        try:
            return client.documents.get(
                space, name, fields={"documents": "@all"}
            )
        except polarion_api.PolarionApiBaseException as e:
            if e.args[0] == 404:
                return None
            raise e

    def load_polarion_documents(
        self,
        document_infos: t.Iterable[data_models.DocumentInfo],
    ) -> polarion_repo.DocumentRepository:
        """Load the documents referenced and text work items from Polarion."""
        return {
            (di.project_id, di.module_folder, di.module_name): (
                self.get_document(
                    di.module_folder, di.module_name, di.project_id
                ),
                self._get_client(di.project_id).work_items.get_all(
                    WORK_ITEMS_IN_PROJECT_QUERY.format(
                        project=di.project_id
                        or self.polarion_params.project_id,
                        doc_folder=di.module_folder,
                        doc_name=di.module_name,
                        wi_type=di.text_work_item_type,
                    ),
                    fields={"workitems": f"id,{di.text_work_item_id_field}"},
                ),
            )
            for di in document_infos
        }

    def _create_and_update_text_work_items(
        self,
        work_items: dict[str, polarion_api.WorkItem],
        client: polarion_api.ProjectClient,
    ):
        client.work_items.update(
            [work_item for work_item in work_items.values() if work_item.id]
        )
        client.work_items.create(
            [
                work_item
                for work_item in work_items.values()
                if not work_item.id
            ]
        )
