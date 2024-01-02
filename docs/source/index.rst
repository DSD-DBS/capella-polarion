..
   Copyright DB InfraGo AG and contributors
   SPDX-License-Identifier: Apache-2.0

capella2polarion
================

A tool to migrate Capella content to a Polarion project as work items.

Diagrams
--------
Migrate diagrams from a diagram cache (pipeline artifact from a capella diagram
cache) job run to Polarion as work items. The whole folder with the
``index.json`` and the SVGs is needed.

Model-Elements
--------------
Migrate any model element from a ``capellambse.MelodyModel`` to Polarion as a
work item. With appropriate :ref:`configuration <config>` on Polarion and an
according config YAML file, any attribute on the capellambse object can be
migrated as a work item link if (and only if) the target object exists as a
work item already. In order to generate diagram references, make sure to
execute the model-elements migration after the diagram migration.

.. toctree::
   :maxdepth: 2
   :caption: Configuration:

   configuration

.. toctree::
   :maxdepth: 3
   :caption: API reference

   code/modules
