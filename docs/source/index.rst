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

With appropriate :ref:`configuration <capella2polarion-config>` on Polarion and
an according config YAML file for capella2polarion any model element can be
migrated from a Capella model to a Polarion project. For an overview over all
features and supported Capella object types have a look into the :ref:`features
and roadmap <features>` documentation page.

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
   :maxdepth: 2
   :caption: Features and Roadmap:

   features

.. toctree::
   :maxdepth: 3
   :caption: API reference

   code/modules
