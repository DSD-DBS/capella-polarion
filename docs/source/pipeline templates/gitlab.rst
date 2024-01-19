..
   Copyright DB InfraGO AG and contributors
   SPDX-License-Identifier: Apache-2.0

GitLab CI/CD pipeline Template
------------------------------

The capella2polarion library can be used in a CI/CD pipeline. For that the
following template can be used inside the `.gitlab-ci.yml` file:

.. literalinclude:: ../../../ci-templates/gitlab/synchronise_elements.yml
   :language: yaml
   :lines: 4-

We highly recommend using the diagram cache as a separate job and defined it as a dependency in our template for that
reason. The diagram cache artifacts have to be included in the capella2polarion job and its path must be defined in the
`CAPELLA2POLARION_MODEL_JSON` variable. A `.gitlab-ci.yml` with a capella2polarion synchronization job could look like
this:

.. code:: yaml

    include:
        - remote: https://raw.githubusercontent.com/DSD-DBS/capella-dockerimages/${CAPELLA_DOCKER_IMAGES_REVISION}/ci-templates/gitlab/diagram-cache.yml
        - remote: https://raw.githubusercontent.com/DSD-DBS/capella-polarion/ci-templates/gitlab/synchronise_elements.yml

    default:
        tags:
            - docker

    workflow: # Control job triggering
        rules:
            - if: $CI_COMMIT_BRANCH == "main" # execution only on main

    variables:
        CAPELLA_VERSION: 6.1.0
        ENTRYPOINT: model.aird
        CAPELLA2POLARION_PROJECT_ID: syncproj
        CAPELLA2POLARION_MODEL_JSON: '{"path": "PATH_TO_CAPELLA", "diagram_cache": "./diagram_cache"}'
        CAPELLA2POLARION_CONFIG: capella2polarion_config.yaml
        CAPELLA2POLARION_DEBUG: 1
