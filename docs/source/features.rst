..
   Copyright DB InfraGO AG and contributors
   SPDX-License-Identifier: Apache-2.0

.. _features:

How it works
============
The synchronization of Capella objects as Polarion work items is done by using
the Polarion REST API. We developed a `Python client`_ where most of the
endpoints are generated from the open API description. In general we serialize
all Capella objects fetched from the ``capellambse.MelodyModel`` instance
inferred from the capella2polarion config. Then in order to reduce the request
amount we compare a checksum of the existing work items and the newly created
ones. If the checksum differs a patch request will happen. If there doesn't
exist a work item with a ``capella_uuid`` yet, a new work item will be created.
These custom fields ``_checksum`` and ``_capella_uuid`` are required.
Per default capella2polarion will not delete any work items but set the status
to deleted. With the ``--delete`` flag however you can enable the deletion.

.. _Python client: https://github.com/DSD-DBS/capella-polarion-template#polarion-dbs-project-template

Features
--------

Supported Capella types
***********************

Capella2Polarion lets you synchronize the following attributes through the
specific serializer alone:

+--------------------------------------+------------------------------------------------------+
| Serializer                           | Description                                          |
+======================================+======================================================+
| generic_work_item                    | The default serializer for Capella objects w/o a     |
|                                      | specific serializer. All other serializers are       |
|                                      | reusing the generic serializer.                      |
|                                      | This serializer populates: type, title,              |
|                                      | description, status, uuid_capella amd                |
|                                      | requirement_types. The requirement type fields       |
|                                      | are inferred from the requirement type (this is      |
|                                      | the custom field name/id) and the value is then      |
|                                      | the requirement's text.                              |
+--------------------------------------+------------------------------------------------------+
| diagram                              | A serializer for Capella diagrams. Currently the     |
|                                      | diagram is taken from the diagram_cache, served      |
|                                      | from a GitLab artifact URL and attached as SVG and   |
|                                      | PNG.                                                 |
|                                      | You can provider ``render_params`` in the config and |
|                                      | these will be passed to the render function of       |
|                                      | capellambse.                                         |
+--------------------------------------+------------------------------------------------------+
| include_pre_and_post_condition       | A serializer adding post- and precondition           |
|                                      | fields. Usually taken for ``Capability`` s.          |
+--------------------------------------+------------------------------------------------------+
| linked_text_as_description           | A serializer resolving ``Constraint`` s and their    |
|                                      | linked text.                                         |
+--------------------------------------+------------------------------------------------------+
| add_context_diagram                  | A serializer adding a context diagram to the work    |
|                                      | item. This requires node.js to be installed.         |
|                                      | The Capella objects where ``context_diagram`` is     |
|                                      | available can be seen in the `context-diagrams       |
|                                      | documentation`_.                                     |
|                                      | You can provider ``render_params`` in the config and |
|                                      | these will be passed to the render function of       |
|                                      | capellambse.                                         |
+--------------------------------------+------------------------------------------------------+
| add_tree_view                        | A serializer adding a tree view diagram to the       |
|                                      | work item. Same requirements as for                  |
|                                      | ``add_context_diagram``. `Tree View Documentation`_. |
|                                      | You can provider ``render_params`` in the config and |
|                                      | these will be passed to the render function of       |
|                                      | capellambse.                                         |
+--------------------------------------+------------------------------------------------------+

.. _context-diagrams documentation: https://dsd-dbs.github.io/capellambse-context-diagrams/#context-diagram-extension-for-capellambse
.. _Tree View documentation: https://dsd-dbs.github.io/capellambse-context-diagrams/tree_view/

Links
*****

Attributes on Capella objects referencing other Capella objects are rendered
as linked work items if (and only if) the link target exists as a work item in
Polarion. This needs specific configuration in the work item link roles XML.
If the configuration is done, any attribute can be rendered as a link.

Grouped linked work items
*************************

In a Polarion live-doc there is no way to filter the linked work items table
which is automatically created from Polarion and can be included into the
document. Therefore Capella2Polarion creates two custom fields for each link
group: A direct field with a list of the links and a field for the reverse
links on each target.

Roadmap
-------

We try to work on all issues listed in the `GitHub issues board`_. However in
the nearest future (max. 2 weeks) we want to solve the following problems:

- Instead of embedding SVGs in the description > attach the SVG and optionally
  a PNG. Additonal checksums are made for the work item and each individual
  attachment.
- New serializers > support of more Capella types
- Improved logging for CI/CD Pipeline verbosity
- Bug fixes...

It is planned that with the end of April 2024 Capella2Polarion will be
published and available via PyPI.

.. _GitHub issues board: https://github.com/DSD-DBS/capella-polarion/issues
