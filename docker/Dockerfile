# The project environment: FreeCAD 1.1.3 (headless), the blwfish FreeCAD MCP server, Newton and these tools.
# Build from the repository root:  docker build -f docker/Dockerfile -t ar4-twin .
FROM mambaorg/micromamba:2.3.0
USER root
RUN apt-get update && apt-get install -y --no-install-recommends git xvfb libgl1 libegl1 && rm -rf /var/lib/apt/lists/*
RUN micromamba install -y -n base -c conda-forge python=3.11 "freecad=1.1.3" pip && micromamba clean -afy
ENV PATH=/opt/conda/bin:$PATH
RUN pip install --no-cache-dir "mcp==2.3.0" "newton[sim]==1.7.0" "warp-lang==1.18.0" trimesh pytest
# blwfish/freecad-mcp v8.4.0, pinned by commit
ARG BLWFISH_COMMIT=7fc5d8fa5186c060ec868183567cf100c717fa66
RUN git clone https://github.com/blwfish/freecad-mcp.git /opt/blwfish && git -C /opt/blwfish checkout ${BLWFISH_COMMIT} \
 && pip install --no-cache-dir -r /opt/blwfish/requirements.txt
# kdb-tools, pinned by tag: okf-validate and okf-ground, with this project's ar4 profile
RUN pip install --no-cache-dir "kdb-tools @ git+https://github.com/aegean-ai/kdb-tools@v0.4.0"
COPY pyproject.toml README.md /opt/twin/
COPY src /opt/twin/src
RUN pip install --no-cache-dir "/opt/twin[sim]"
COPY docker/entrypoint.sh /usr/local/bin/twin-entrypoint
COPY docker/twin-blwfish /usr/local/bin/twin-blwfish
# FreeCAD reads its home directory from the passwd database, so the entrypoint adds the container user.
RUN chmod 666 /etc/passwd && chmod 755 /usr/local/bin/twin-entrypoint /usr/local/bin/twin-blwfish
ENTRYPOINT ["/usr/local/bin/twin-entrypoint"]
CMD ["bash"]
WORKDIR /work
