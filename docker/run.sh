#!/bin/bash
# Run a command in the project container with this repository mounted at /work.
#   docker/run.sh twin-check twin/build.py
#   docker/run.sh twin-blwfish            # an MCP server on stdio, for your agent's MCP config
cd "$(dirname "$0")/.."
exec docker run --rm -i -v "$PWD:/work" -w /work --user "$(id -u):$(id -g)" "${TWIN_IMAGE:-ar4-twin}" "$@"
