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

__ https://dbinfrago.github.io/py-capellambse/code/capellambse.model.layers.html

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
   :lines: 37-38

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
   :lines: 13-17

or ``SystemFunction`` with the ``add_context_diagram`` serializer using ``filters``:

.. literalinclude:: ../../../tests/data/model_elements/config.yaml
   :language: yaml
   :lines: 68-71

Jinja as Description
^^^^^^^^^^^^^^^^^^^^

The ``add_jinja_as_description`` serializer allows you to completely replace
the default description content with the output of a rendered Jinja2 template.
This provides maximum flexibility for customizing the main content area of your
Work Items enabling HTML structures like tables, lists and more in it.

You need to specify the path to the template file. Optionally, you can also
provide the folder containing the template and any parameters required by the
template for rendering.

.. code-block:: yaml

   serializer:
     add_jinja_as_description:
       template_folder: path/to/your/templates
       template_path: description_template.html.j2
       render_parameters:
         custom_var: "some_value"
         another_param: true

Jinja Fields
^^^^^^^^^^^^

The ``add_jinja_fields`` serializer enables populating specific custom fields
in Polarion with content generated from Jinja2 templates. This is useful for
adding structured, dynamically generated information to Work Items beyond the
standard description or splitting HTML structures from the description to a
dedicated custom field.

For each custom field provide its Polarion ID as a key. The value should be a
dictionary specifying the ``template_path``, and optionally the
``template_folder`` and any ``render_parameters`` needed by that template.

.. code-block:: yaml

   serializer:
     add_jinja_fields:
       field_id:
         template_folder: folder/path
         template_path: template.html.j2
         render_parameters:
           key: "value"
       field_id_1:
         template_folder: folder/path
         template_path: template_1.html.j2

If a serializer supports additional parameters this will be documented in the
supported capella serializers table in :ref:`Model synchronization
<supported_capella_serializers>`.

Different capella type and polarion type ID
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. literalinclude:: ../../../tests/data/model_elements/config.yaml
   :language: yaml
   :lines: 33-34

Sometimes capellambse class types are not the same in Polarion. In order to
handle this case you can use the ``polarion_type`` key to map capellambse types
to the desired Polarion type.

.. literalinclude:: ../../../tests/data/model_elements/config.yaml
   :language: yaml
   :lines: 77-99

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
   :lines: 33-36

However there is a more verbose way that gives you the option to configure the
link further:

.. literalinclude:: ../../../tests/data/model_elements/config.yaml
   :language: yaml
   :lines: 56-63

In this example the ``capella_attr`` is utilizing the map functionality of
capellambse. You can therefore chain attributes using a ``.`` to get to the
desired elements for your link.

Grouped Link Custom Fields
^^^^^^^^^^^^^^^^^^^^^^^^^^
The grouped link custom fields can be configured globally or on a per-link
basis. By default, if no specific configuration is provided, the system will
check the ``CAPELLA2POLARION_GROUPED_LINKS_CUSTOM_FIELDS`` environment
variable. If this variable is set to ``true``, grouped link custom fields will
be generated for **all** links. If it is set to ``false`` or not set at all,
grouped link custom fields will not be generated for links where the following
properties are not configured.

To explicitly control the generation of grouped link custom fields, you can use
the ``link_field`` and ``reverse_field`` properties within the ``LinkConfig``
in your synchronization configuration YAML:

* **`link_field`**: If set, a grouped forward link custom field (e.g.
  ``inputExchanges``) will be created for the Capella element with the
  specified name. The value is the polarion custom field ID for a grouped list
  of these links.
* **`reverse_field`**: If set, a grouped backlink custom field (e.g.
  ``inputExchangesReverse``) will be created on the target work item with the
  specified name. The value is the polarion custom field ID for the grouped
  backlinks of the links.

If both ``link_field`` and ``reverse_field`` are omitted or set to ``None`` in
the ``LinkConfig``, and the ``CAPELLA2POLARION_GROUPED_LINKS_CUSTOM_FIELDS``
environment variable is *not* set to ``true``, then no grouped link custom
fields will be generated for that specific link.

Includes
^^^^^^^^
The ``include`` is an optional feature that renders additional work item
references into the grouped link custom field. In this example for each linked
``FunctionalExchange`` in the grouped list there will be ``ExchangeItem`` s
included. The key "Exchange Items" is used for the indication in the list.
