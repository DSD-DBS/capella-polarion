..
   Copyright DB InfraGO AG and contributors
   SPDX-License-Identifier: Apache-2.0

.. _capella2polarion-config:

YAML
====
To control the migration of model elements, the following YAML file serves as a
configuration for the capella2polarion service. In this file, you can specify
the layer, the type in Polarion, the class type for matching objects in
capellambse, the serializer to use. If an item is a dictionary, it means there
are work item links to be migrated. Make sure to use the attribute names on the
capellambse object correctly.

.. literalinclude:: ../../tests/data/model_elements/config.yaml
   :language: yaml
   :lines: 4-

The first section is a general configuration where you can set links to be
migrated for all class types. For example, ``parent`` and
``description_reference`` are links that will be applied to all specified class
types. Since ``Class`` is a common type that exists in all layers, links
specific to ``Class`` can be specified here to avoid duplication within the
file.

.. _polarion-config:

Polarion
========
In general, if an attribute is not configured, it will not be accepted and the
the Rest API will raise a 404 HTTPError since it expects a plain string
attribute. However, to be able to make ``GET`` requests, you need to configure
your Polarion project correctly. For that there is the `Polarion DBS Project
Template`_ which includes icon, custom field and enumeration configuration for
a pleasant capella2polarion synchronization.

.. _Polarion DBS Project Template: https://github.com/DSD-DBS/capella-polarion-template#polarion-dbs-project-template

In the following are some requirements for the configuration if you don't want
to use the Project Template:

The matching of diagrams and model elements is done using the ``uuid_capella``
attribute, which needs to be declared in the ``Custom Fields`` section. Simply
choose ``All Types`` for this attribute.

To have icons for your model elements, you need to declare the work item type
in the ``workitem-type-enum.xml`` file in the Polarion administration panel and
upload a 16x16 picture file.

To generate clickable linked work items, you need to configure the link role
enumerations in the ``workitem-link-role-enum.xml`` file. Here, the ID should
match the attributes of the capellambse object (e.g., ``involved_activities``),
or you can define custom attributes that require custom code implementation
(e.g., ``description_reference`` links for references to objects in the
description).
