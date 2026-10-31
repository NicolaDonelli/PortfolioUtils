# syntax=docker/dockerfile:1

ARG PY_VERSION=3.13
FROM python:${PY_VERSION}-buster
ARG PKG_VERSION

WORKDIR /portfolio-utils

# RUN apt-get update && apt-get upgrade -y && apt-get install make git gcc libpq-dev -y --no-install-recommends

COPY LICENSE MANIFEST.in pyproject.toml README.md Makefile ./
COPY sphinx sphinx
COPY portfolio_utils portfolio_utils
COPY tests tests

RUN addgroup --system tester && adduser --system --group tester
RUN chown -R tester:tester /portfolio-utils

# change to the tester user: switch to a non-root user is a best practice.
USER tester
ENV PATH ${PATH}:/home/tester/.local/bin
ENV SETUPTOOLS_SCM_PRETEND_VERSION=$PKG_VERSION

CMD make checks
