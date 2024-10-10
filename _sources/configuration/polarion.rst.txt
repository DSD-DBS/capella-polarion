..
   Copyright DB InfraGO AG and contributors
   SPDX-License-Identifier: Apache-2.0

.. _polarion-config:

Polarion
========
In general, if an attribute is not configured, it will not be accepted and the
the Rest API will raise a 400 HTTPError since it expects a plain string
attribute. As we use rich text instead, you need to configure your Polarion
project correctly. For that there is the `Capella2Polarion Project Template`_
which includes icon, custom field and enumeration configuration for a pleasant
capella2polarion synchronization.

.. _Capella2Polarion Project Template: https://github.com/DSD-DBS/capella-polarion-template#polarion-dbs-project-template

In general it is advised to use a separate Polarion project for the model
synchronization. In the following are some requirements for the configuration
if you don't want to use the Project Template:

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
