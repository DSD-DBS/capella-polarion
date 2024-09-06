..
   Copyright DB InfraGO AG and contributors
   SPDX-License-Identifier: Apache-2.0

.. _render-documents:

Render Polarion Live-Documents
==============================
The `capella2polarion` service supports rendering and updating Polarion Live
Documents in two distinct modes: Full authority and Mixed authority. These
modes control how sections of the Live Document (Live-Doc) are populated and
managed. References to the work items from the model elements synchronization
are resolved automatically. The service is able to populate Live-Doc spaces
completely on its own, managing the complexity of the document layout
configuration for each work item type. The only thing needed for the service is
a dedicated Polarion document space, ``_default`` can be used too.

How it works
------------


Full Authority Mode
*******************
In Full authority mode, the entire Live-Doc is controlled by the
`capella2polarion` service. During each rendering session, the entire document
is re-rendered and updated based on the data provided by the Capella model. Any
manual edits or changes made by a user in Polarion will be overwritten during
the next synchronization process.

This mode ensures that the Live-Doc is always consistent with the Capella
model and Polarion project state, but it means that no manual changes can
persist between rendering sessions.