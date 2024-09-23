
..
   Copyright DB InfraGO AG and contributors
   SPDX-License-Identifier: Apache-2.0

Polarion config diff/mig tool
=============================
The model element synchronization is a service that requires configuration
either in C2P or in Polarion. While doing these synchronizations for multiple
projects, we notice that the effort to maintain the configurations, either
C2P or on Polarion side, increases. Therefore we want to develop an application
that enables Polarion admins to visualize differences of Polarion configuration
files over multiple projects. In the end it should also automate migrations of
updates and changes to the configuration files.

C2P configuration frontend
==========================
For improving the quality of life for setting up the synchronization of C2P
a nice frontend could automate the generation of the configuration YAML file,
plus a minimal set of configuration XML files needed for Polarion. Before
generation it would be also beneficial to validate the C2P config, on Capella
types, serializers and attributes (links). The latter already happens partially
loading the config.

Bug-Fixes, issues and requests
==============================
We try to work on all issues listed in the `GitHub issues board`_. Additionally
since C2P is open-source we want to know about the feedback of our external
users. We are curious about the ideas and feature requests you might come up
with ❤️.

.. _GitHub issues board: https://github.com/DSD-DBS/capella-polarion/issues
