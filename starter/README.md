# Starter for your AR4 twin agent

Copy this directory into your own project repository to start your agent. It holds the plumbing,
so you can spend your time on reading the documents well and on building the parts.

```bash
cp -r starter/ ../my-twin-agent && cd ../my-twin-agent
cp kdb.toml.example kdb.toml     # point it at your model server
uv sync
uv run pytest                    # offline: a scripted model stands in for the server, and no FreeCAD runs
```

## What it does

`twin` is the command, with `ingest` and `cad` (`twinagent/cli.py`). The model server comes from
`kdb.toml`: a local server or OpenRouter. Name the environment variable that holds your API key in
`api_key_env`. The starter refuses a key written in the file.

`ingest` (`twinagent/ingest.py`) reads a PDF three pages at a time, or a spreadsheet one sheet at a
time. Each number comes back typed: the part it belongs to, the page type, a quantity name, the
number and a unit from `twin_tools.units`. A number from text carries its quote and page, and one
from a spreadsheet carries its cell and value. The agent sends back any quote that is not on its
page, any cell that does not hold the value, and any unit outside the list.

`cad` (`twinagent/cad.py`) gives the model the FreeCAD server's tools and a `read_page` tool for
kDB pages. The model builds one link, saves the FreeCAD document and exports an STL mesh. With
its answer it states the volume, the bounding box size and the number of through holes it
expects. `twinagent/solid.py` measures the mesh, checks that it is one closed piece and compares
it with that expectation. The files go into `cad/` only when they agree. This catches a cut made
in the wrong place or silently lost by FreeCAD. It cannot catch an expectation that is wrong in
the same way as the geometry.

## What is yours

For the kDB: the instructions, which pages to read, tables inside the PDFs, merging the same part
across documents, formulas for derived values such as a joint's velocity limit, and writing the
pages with their sources and highlights, `index.md` and `log.md`. `write_pages` raises
`NotImplementedError` until you write it.

For the parts: instructions that make each link parametric, with its dimensions in a spreadsheet
bound to the sketches, so that a changed kDB value rebuilds the part. Add stronger checks against
the kDB, such as the positions of the bores, because blwfish reports some failures as success (see
the known issues in the project README).

For the twin: `twin/build.py`, with the links' frames, the joint axes, and every number read from
the kDB with `twin_tools.kdb.si`.
