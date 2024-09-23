..
   Copyright DB InfraGO AG and contributors
   SPDX-License-Identifier: Apache-2.0

.. _sync-config:

Model synchronization
=====================
To control the migration of model elements, the following YAML file serves as a
configuration for the capella2polarion service. In this file, you can specify
the layer, class types and attributes for matching Capella model elements.
Additionally you have the control of adding relationships with the links key.
Underneath the links key use attributes on the matched capellambse model
object. Make sure that the attribute name is correct, you can use
`capellambse's documentation`__ for that.

__ https://dsd-dbs.github.io/py-capellambse/code/capellambse.model.layers.html

Generic
-------

.. literalinclude:: ../../../tests/data/model_elements/config.yaml
   :language: yaml
   :lines: 4-26

The "star" section is a general configuration where you can set links to be
migrated for all class types. For example, ``parent`` and
``description_reference`` are links that will be applied to all specified class
types. Since ``Class`` is a common class type that exists in all layers, links
specific to ``Class`` can be specified here to avoid duplication. This will be
merged into layer specific configuration for ``Class`` if there is any.

Serializers
-----------

.. literalinclude:: ../../../tests/data/model_elements/config.yaml
   :language: yaml
   :lines: 33-34

With ``serializer`` you can control which function is called to render the
:py:class:`capella2polarion.data_models.CapellaWorkItem`. There is a generic
serializer including title (name), description and requirement types, taken per
default. You may also define multiple serializers by providing a list of
serializers in the configs. These will be called in the order provided in the
list. Some serializers also support additional configuration. This can be done
by providing a dictionary of serializers with the serializer as key and the
configuration of the serializer as value. For example ``Class`` using the
``add_tree_diagram`` serializer:

.. literalinclude:: ../../../tests/data/model_elements/config.yaml
   :language: yaml
   :lines: 9-13

or ``SystemFunction`` with the ``add_context_diagram`` serializer using ``filters``:

.. literalinclude:: ../../../tests/data/model_elements/config.yaml
   :language: yaml
   :lines: 64-67

If a serializer supports additional parameters this will be documented in the
supported capella serializers table in :ref:`Model synchronization
<supported_capella_serializers>`.

Different capella type and polarion type ID
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. literalinclude:: ../../../tests/data/model_elements/config.yaml
   :language: yaml
   :lines: 29-30

Sometimes capellambse class types are not the same in Polarion. In order to
handle this case you can use the ``polarion_type`` key to map capellambse types
to the desired Polarion type.

.. literalinclude:: ../../../tests/data/model_elements/config.yaml
   :language: yaml
   :lines: 73-91

For the ``PhysicalComponent`` you can see this in extreme action, where based
on the different permutation of the attributes actor and nature different
Polarion types are used. In capellambse however this is just a
``PhysicalComponent``. Combining this with ``links`` is possible too. You can
configure a generic config and for each specific config you can also add a
``links`` section. Both will be merged.

.. _links-config:

Links
-----
Links can be configured by just providing a list of strings:

.. literalinclude:: ../../../tests/data/model_elements/config.yaml
   :language: yaml
   :lines: 33-37

However there is a more verbose way that gives you the option to configure the
link further:

.. literalinclude:: ../../../tests/data/model_elements/config.yaml
   :language: yaml
   :lines: 52-63

The links of ``SystemFunction`` are configured such that a ``polarion_role``,
a separate ``capella_attr``, an ``include``, ``link_field`` and
``reverse_field`` is defined. In this example the ``capella_attr`` is utilizing
the map functionality of capellambse. You can therefore chain attributes using
a ``.`` to get to the desired elements for your link. The ``link_field`` is the
polarion custom field ID for a grouped list of these links. The
``reverse_field`` is the polarion custom field ID for the grouped backlinks of
the links. The ``include`` is an optional feature that renders additional
work item references into the grouped link custom field. In this example for
each linked ``FunctionalExchange`` in the grouped list there will be
``ExchangeItem`` s included. The key "Exchange Items" is used for the
indication in the list.
