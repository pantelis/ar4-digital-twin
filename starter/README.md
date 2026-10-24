# Starter for your AR4 twin agent

Copy this directory into your own project repository to start your agent. It holds the plumbing
every solution needs, so you can spend your time on reading the documents well and on building
the parts.

```bash
cp -r starter/ ../my-twin-agent && cd ../my-twin-agent
cp kdb.toml.example kdb.toml     # point it at your model server
uv sync
uv run pytest                    # offline: a scripted model stands in for the server, and no FreeCAD runs
```

## What it does

Most of the plumbing comes from the `agent` extra of
[kdb-tools](https://github.com/aegean-ai/kdb-tools), which the Introduction to AI project uses
too. `kdb_tools.config` reads the model server from `kdb.toml`, a local server or OpenRouter,
and refuses an API key written in the file. Name the environment variable that holds the key
in `api_key_env`. `kdb_tools.guard` refuses a prompt the server would cut.

`twinagent/ingest.py` reads a PDF three pages at a time, or a spreadsheet one sheet at a time,
with the kdb-tools extraction agent. Each number comes back typed: the part it belongs to, the
page type, a quantity name, the number and a unit from `twin_tools.units`. A number read from
text carries its quote and page, and one read from a spreadsheet carries its cell and value.
The agent sends back any quote that is not on its page, any cell that does not hold the value,
and any unit outside the list.

`twinagent/cad.py` gives an agent the FreeCAD server's tools, through `twinagent/freecad.py`, and
a `quantities` tool that reads a kDB page. The agent models one link, saves the FreeCAD document
and exports an STL mesh. Its output validator checks that both files exist and copies them into
`cad/`. `twinagent/freecad.py` starts the server with the command in `kdb.toml`, by default
`docker/run.sh twin-blwfish`, and sends back any result that carries an error.

`twinagent/cli.py` is the `twin` command, with `ingest` and `cad`.

## What is yours

Everything that turns this into a kDB and a twin. For the kDB: the instructions, which pages to
read, tables inside the PDFs, merging the same part across documents, formulas for derived values
such as a joint's velocity limit from its motor and gearbox, and writing the pages with their
sources and highlights, `index.md` and `log.md`. `write_pages` raises `NotImplementedError` until
you write it.

For the parts: instructions that make each link parametric, with its dimensions in a
spreadsheet bound to the sketches, so that a changed kDB value rebuilds the part. Checking the
solid the agent built against the kDB is yours too, because blwfish reports some failures as
success; the project README lists them. Then `twin/build.py`: the links' frames, the joint axes,
and every number read from the kDB with `twin_tools.kdb.si`.

The project page lists everything the twin and the program must do, and how they are graded.
