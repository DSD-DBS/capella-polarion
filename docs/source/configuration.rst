..
   Copyright DB InfraGO AG and contributors
   SPDX-License-Identifier: Apache-2.0

.. _config:

YAML
====
To control the migration of model elements, you can use the following YAML
file. In this file, you can specify the layer and class type for matching
objects. If an item is a dictionary, it means there are work item links to be
migrated. Make sure to use the attribute names on the capellambse object
correctly.

.. literalinclude:: ../../tests/data/model_elements/config.yaml
   :language: yaml
   :lines: 4-

The first section is a general configuration where you can set links to be
migrated for all class types. For example, ``parent`` and ``description_reference``
are links that will be applied to all specified class types. Since ``Class`` is a
common class type that exists in all layers, links specific to ``Class`` can be
specified here to avoid duplication.

Polarion
========
In general, if an attribute is not configured, it will still be accepted and
created via the Rest API. However, to be able to make ``GET`` requests, you
need to configure your Polarion project correctly. The matching of diagrams and
model elements is done using the ``uuid_capella`` attribute, which needs to be
declared in the ``Custom Fields`` section. Simply choose ``All Types`` for this
attribute.

To have icons for your model elements, you need to declare the work item type
in the ``workitem-type-enum.xml`` file in the Polarion administration panel.
This file is an enumeration file where the work item type IDs should follow the
camel case pattern (e.g., ``operationalCapability`` for
``OperationalCapability``).

To generate clickable linked work items, you need to configure the link role
enumerations in the ``workitem-link-role-enum.xml`` file. Here, the ID should
match the attributes of the capellambse object (e.g., ``involved_activities``),
or you can define custom attributes that require custom code implementation
(e.g., ``description_reference`` links for references to objects in the
description).
