..
   Copyright DB InfraGO AG and contributors
   SPDX-License-Identifier: Apache-2.0

capella2polarion
================

A tool to migrate Capella content to a Polarion project as work items.

Synchronization of Model-Elements
---------------------------------

Migrate any model element from a ``capellambse.MelodyModel`` to Polarion as a
work item. Diagrams are taken from a diagram cache (pipeline artifact from a
`capella diagram cache`_) job run to Polarion as work items. The whole folder
with the ``index.json`` and the SVGs is needed for the diagram synchronization.
The SVG and a PNG of it are attached to the respective work item.

With appropriate :ref:`configuration <capella2polarion-config>` on Polarion
and an according :ref:`config YAML file <polarion-config>` for
capella2polarion any model element can be migrated from a Capella model to a
Polarion project. Attributes are migrated as links and text from requirements
and link groups are synchronized as custom fields.

The synchronization works by comparing the checksum of work items. If they
differ the old will be patched by the new one.

.. _capella diagram cache: https://github.com/DSD-DBS/capella-dockerimages/blob/main/ci-templates/gitlab/diagram-cache.yml

.. toctree::
   :maxdepth: 2
   :caption: Configuration:

   configuration

.. toctree::
   :maxdepth: 2
   :caption: CI/CD Template:

   pipeline templates/gitlab

.. toctree::
   :maxdepth: 3
   :caption: API reference

   code/modules
