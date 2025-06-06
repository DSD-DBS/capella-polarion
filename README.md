<!--
 ~ Copyright DB InfraGO AG and contributors
 ~ SPDX-License-Identifier: Apache-2.0
 -->

# capella2polarion

<!-- prettier-ignore -->
![image](https://github.com/DSD-DBS/capella-polarion/actions/workflows/build-test-publish.yml/badge.svg)
![image](https://github.com/DSD-DBS/capella-polarion/actions/workflows/lint.yml/badge.svg)
![image](https://github.com/DSD-DBS/capella-polarion/actions/workflows/docs.yml/badge.svg)

Synchronise Capella models with Polarion projects.

![image](./docs/source/_static/c2p-uc1.gif)

Use cases covered:

- _Make Capella Objects and attributes of interest available in a Polarion_ project so that a Project User could referense those objects and attributes in LiveDocs and WorkItems such as requirements, to ensure consistency across the Project. Model has full authority over the work items that represent model elements. A change to a model element will result in a change to the corresponding WorkItem in Polarion.

- _Create and maintain LiveDocs_ based on a Capella model and a set of templates so that the Project Users could do less paperwork. A change to the model or template shall result in a change to a LiveDoc or related WorkItems. All changes to generated LiveDocs made in Polarion will be over-written by Capella2Polarion as it has "Full Authority" over those documents.

- _Create and co-maintain LiveDocs_ where model would have authority over some sections and people over other sections (mixed-authority) - this would enable Project User to create requirements or other objects in the context of model-derived structure or elements.

# Documentation

<!-- prettier-ignore -->
Read the [full documentation on GitHub](https://dsd-dbs.github.io/capella-polarion).

# Installation

We have a dependency on [cairosvg](https://cairosvg.org/). Please check their
[documentation](https://cairosvg.org/documentation/) for OS specific dependencies.

You can install the latest released version directly from [PyPI](https://pypi.org/project/capella2polarion/).

```sh
pip install capella2polarion
```

# Contributing

We'd love to see your bug reports and improvement suggestions! Please take a
look at our [guidelines for contributors](CONTRIBUTING.md) for details. It also
contains a short guide on how to set up a local development environment.

# Licenses

This project is compliant with the
[REUSE Specification Version 3.0](https://git.fsfe.org/reuse/docs/src/commit/d173a27231a36e1a2a3af07421f5e557ae0fec46/spec.md).

Copyright DB InfraGO AG, licensed under Apache 2.0 (see full text in
[LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt))

Dot-files are licensed under CC0-1.0 (see full text in
[LICENSES/CC0-1.0.txt](LICENSES/CC0-1.0.txt))
