..
   Copyright DB InfraGO AG and contributors
   SPDX-License-Identifier: Apache-2.0

.. _render-documents:

Render Live-Docs
================
The `capella2polarion` service supports rendering and updating Polarion Live
Documents in two distinct modes: Full authority and Mixed authority. These
modes control how sections of the Live Document (Live-Doc) are populated and
managed. References to the work items from the model elements synchronization
are resolved automatically. The service is able to populate Live-Doc spaces
completely on its own, managing the complexity of the document layout
configuration for each work item type. The only thing needed for the service is
a dedicated Polarion document space, ``_default`` can be used too.

The setup and configuration is explained in detail in the :ref:`Live-Docs
rendering <render-docs-config>` documentation page.

Full Authority Mode
*******************
In Full authority mode, the entire Live-Doc is controlled by the
`capella2polarion` service. During each rendering session, the entire document
is re-rendered and updated based on the data provided by the Capella model. Any
manual edits or changes made by a user in Polarion will be overwritten during
the next synchronization process if the status is still set to a value in the
``status_allow_list``. Don't worry comments will persist because everything in
the rendered Live-Doc is a work item. Headings are reused, free text will be
created as a work item of type Text. The status feature enables an efficient
and streamlined review and release process, minimizing disruptions during the
phases.

It is ensured that the Live-Doc is always consistent with the Capella model and
Polarion project state, but it means that no manual changes can persist between
rendering sessions.

Mixed Authority Mode
********************
In mixed authority mode, users have more flexibility over the Live-Doc. Users
can mark specific sections of the Live-Doc via wiki-macro where they would like
content to be inserted or updated by the `capella2polarion` service. If you
want to see how this looks like, have a look in the :ref:`configuration
documentation page <mixed-sections-config>`. These sections are populated with
content rendered from Jinja2 templates, while the rest of the document can be
manually managed and updated by users in Polarion.

This allows users to maintain manual changes in non-synchronized sections of
the document, while still benefiting from automated updates for key sections
filled with model enhanced content.

If you want to know how to setup the Live-Doc rendering, head to the
:ref:`documentation page <render-docs-config>`.
