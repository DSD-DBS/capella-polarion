<!--
 ~ Copyright DB InfraGo AG and contributors
 ~ SPDX-License-Identifier: Apache-2.0
 -->

# capella2polarion

<!-- prettier-ignore -->
![image](https://github.com/DSD-DBS/capella-polarion/actions/workflows/build-test-publish.yml/badge.svg)

Synchronise Capella models with Polarion projects

# Documentation

<!-- prettier-ignore -->
Read the [full documentation on GitLab pages](https://dsd-dbs.github.io/capella-polarion).

# Installation

You can install the latest released version directly from PyPI (**Not yet**).

```zsh
pip install capella2polarion
```

To set up a development environment, clone the project and install it into a
virtual environment.

```zsh
git clone https://github.com/DSD-DBS/capella-polarion.git
cd capella2polarion
python -m venv .venv

source .venv/bin/activate.sh  # for Linux / Mac
.venv\Scripts\activate  # for Windows

pip install -U pip pre-commit
pip install -e '.[docs,test]'
pre-commit install
```

# Contributing

We'd love to see your bug reports and improvement suggestions! Please take a
look at our [guidelines for contributors](CONTRIBUTING.md) for details.

# Licenses

This project is compliant with the
[REUSE Specification Version 3.0](https://git.fsfe.org/reuse/docs/src/commit/d173a27231a36e1a2a3af07421f5e557ae0fec46/spec.md).

Copyright DB InfraGo AG, licensed under Apache 2.0 (see full text in
[LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt))

Dot-files are licensed under CC0-1.0 (see full text in
[LICENSES/CC0-1.0.txt](LICENSES/CC0-1.0.txt))
