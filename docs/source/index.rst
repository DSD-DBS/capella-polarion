..
   Copyright DB InfraGO AG and contributors
   SPDX-License-Identifier: Apache-2.0

capella2polarion
================
A tool to migrate Capella content to a Polarion project as work items and to
manage Polarion Live-Documents.

Overview
--------
capella2polarion offers several features to interact with Polarion and Capella
models. Currently, the following features are available:

Synchronization of Model-Elements
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Migrate any model element from a ``capellambse.MelodyModel`` to Polarion as a
work item. Diagrams are taken from a diagram cache (pipeline artifact from a
`capella diagram cache`_) job run to Polarion as work items. The whole folder
with the ``index.json`` and the SVGs is needed for the diagram synchronization.

With appropriate :ref:`configuration <sync-config>` of the service and on
:ref:`Polarion <polarion-config>` any model element can be migrated from a
Capella model to a Polarion project. For an overview of all features related to
the synchronization and supported Capella object types, have a look at the
:ref:`model synchronization <sync>` documentation page.

Rendering of Live-Documents
^^^^^^^^^^^^^^^^^^^^^^^^^^^
The `render_documents` command in the CLI allows the rendering of Polarion
Live-Documents in a dedicated documents space inside a Polarion project. This
doesn't need to be the sync project. These documents are generated via
rendering Jinja2 templates, enabling them to be enriched by model data without
requiring the data as a work item in Polarion.

There are two modes for rendering Live-Documents:

- **Full Authority Documents**: C2P takes full control over the content, and
   any human-made changes to the document will be overwritten in the next
   rendering cycle. To make changes persistent, modifications to the Jinja2
   templates are required.

- **Mixed Authority Documents**: C2P takes control over marked sections of
   the document, allowing for collaboration where dedicated model-enhanced
   areas coexist with human-edited content.

Detailed information on the Live-Document rendering feature can be found in the
:ref:`render documents <render-documents>` documentation page. For a guide on
how this service is configured see the :ref:`configuration page
<render-docs-config>`.

.. note:: Additional features will be documented here in the future as they are developed and integrated.

.. _capella diagram cache: https://github.com/DSD-DBS/capella-dockerimages/blob/main/ci-templates/gitlab/diagram-cache.yml

.. toctree::
   :maxdepth: 2
   :caption: Features:

   features/render_documents
   features/sync

.. toctree::
   :maxdepth: 2
   :caption: Configuration:

   configuration/render_documents
   configuration/sync
   configuration/polarion

.. toctree::
   :maxdepth: 2
   :caption: CI/CD Templates:

   pipeline templates/gitlab

.. toctree::
   :maxdepth: 2
   :caption: Roadmap:

   roadmap

.. toctree::
   :maxdepth: 3
   :caption: API reference

   code/modules
