..
   Copyright DB InfraGO AG and contributors
   SPDX-License-Identifier: Apache-2.0

.. _capella2polarion-config:

YAML
====
To control the migration of model elements, the following YAML file serves as a
configuration for the capella2polarion service. In this file, you can specify
the layer, class types and attributes for matching Capella model elements.
Additionally you have the control of adding relationships with the links key.
Underneath the links key use attributes on the matched capellambse model
object. Make sure that the attribute name is correct, you can use
`capellambse's documentation`__ for that.

__ https://dsd-dbs.github.io/py-capellambse/code/capellambse.model.layers.html

.. literalinclude:: ../../tests/data/model_elements/config.yaml
   :language: yaml
   :lines: 4-

The "star" section is a general configuration where you can set links to be
migrated for all class types. For example, ``parent`` and
``description_reference`` are links that will be applied to all specified class
types. Since ``Class`` is a common class type that exists in all layers, links
specific to ``Class`` can be specified here to avoid duplication. This will be
merged into layer specific configuration for ``Class`` if there is any.

With ``serializer`` you can control which function is called to render the
:py:class:`capella2polarion.data_models.CapellaWorkItem`. There is a generic
serializer including title (name), description and requirement types, taken per
default. You may also define multiple serializers by providing a list of
serializers in the configs. These will be called in the order provided in the
list. Some serializers also support additional configuration. This can be
done by providing a dictionary of serializers with the serializer as key and
the configuration of the serializer as value. If a serializer supports
configuration this will be documented in :ref:`features and roadmap <features>`.

Sometimes capellambse class types are not the same in Polarion. In order to
handle this case you can use the ``polarion_type`` key to map capellambse types
to the desired Polarion type. For the ``PhysicalComponent`` you can see this in
action, where based on the different permutation of the attributes actor and
nature different Polarion types are used. In capellambse however this is just a
``PhysicalComponent``. Combining this with ``links`` is possible too. You can
configure a generic config and for each specific config you can also add a
``links`` section. Both will be merged.

Polarion
========
In general, if an attribute is not configured, it will not be accepted and the
the Rest API will raise a 400 HTTPError since it expects a plain string
attribute. As we use rich text instead, you need to configure
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
