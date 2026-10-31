---
name: 'Project configuration files'
description: 'Rules for editing pyproject.toml, Makefile, pre-commit, commitlint, CI workflows and the dev container without weakening quality gates.'
applyTo: 'pyproject.toml,Makefile,.pre-commit-config.yaml,.commitlintrc.yaml,.github/workflows/**,.devcontainer/**'
---
# Project configuration

- These files define the quality standards. Do not relax them (coverage `fail_under`,
  mypy flags, ruff rules, pydoclint options, commitlint rules, pre-commit stages) unless
  the owner explicitly asks. Tightening is welcome when proposed explicitly.
- Dependencies: add runtime packages to `[project].dependencies` and tooling/stubs to
  `[dependency-groups].dev` with a lower bound (`>=x.y`), then run `make setup_dev`
  (and `make reqs` for runtime requirements). Never edit `requirements/*.txt`.
- Keep Python 3.13 consistent across `requires-python`, `.pre-commit-config.yaml`,
  the Dockerfile, the dev container and the workflows.
- Makefile recipes require bash and GNU make; keep tabs for recipe indentation.
