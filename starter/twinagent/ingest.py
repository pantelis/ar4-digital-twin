"""ingest <document>: read the manual, a datasheet or a spreadsheet and add its numbers to the kDB.

What the starter does: it reads a PDF a few pages at a time, or a spreadsheet one sheet at a time,
with the extraction agent from kdb-tools. Its output is typed quantities, each with a unit from
twin_tools.units. A quantity read from text is a kdb_tools.agent.Quote and one read from a
spreadsheet is a kdb_tools.agent.CellValue, so the agent sends back any quote that is not on its
page and any cell that does not hold its value. What is yours: better instructions, which pages
to read, tables in the PDFs, merging the same part across documents, formulas for derived values
such as a joint's velocity limit, and writing the kDB pages, index, log and highlights.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from kdb_tools import guard
from kdb_tools.agent import CellValue, Chunk, Quote, extraction_agent, pdf_chunks, sheet_chunks
from kdb_tools.config import Config, model_from, settings_from
from kdb_tools.sheet import SUFFIXES as SHEETS
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from twin_tools.units import UNITS

Unit = Literal[tuple(UNITS)]


class Stated(BaseModel):
    entity: str = Field(description="the part the number belongs to, named as the document names it, such as J2")
    page_type: Literal["Joint", "Link", "Motor", "Gearbox", "Material"]
    name: str = Field(description="the quantity in snake_case, such as upper_limit, rated_torque, ratio or density")
    number: float = Field(description="the number the document states")
    unit: Unit = Field(description="its unit, written exactly as in the list")


class FromText(Quote, Stated):
    pass


class FromCell(CellValue, Stated):
    pass


class Found(BaseModel):
    from_text: list[FromText] = Field(default_factory=list)
    from_cells: list[FromCell] = Field(default_factory=list)


INSTRUCTIONS = (
    "You read part of a document about the Annin Robotics AR4 robot arm and return every number that a simulation "
    "of the arm needs: joint limits, speeds, torques, gear ratios, masses, dimensions and material densities. "
    "Cite each number: from a PDF, one sentence copied word for word and its page; from a spreadsheet, the cell "
    "that holds it and the value exactly as the cell shows it."
)  # yours to improve


def make_agent(model, root: Path | None = None, settings: dict | None = None) -> Agent[Chunk, Found]:
    """The chunk agent. Given the kDB root, it can also call find_quote, find_value, find_cell and check_pages."""
    return extraction_agent(model, Found, INSTRUCTIONS, root=root, settings=settings)


def chunks(document: Path, pages_per_chunk: int = 3):
    if document.suffix.lower() in SHEETS:
        return sheet_chunks(document)
    return pdf_chunks(document, pages_per_chunk)


def ingest(root: Path, document: Path, cfg: Config) -> Found:
    agent = make_agent(model_from(cfg), root, settings_from(cfg))
    found = Found()
    for chunk, prompt in chunks(document):
        guard.check(prompt, cfg.context)
        out = agent.run_sync(prompt, deps=chunk).output
        found.from_text += out.from_text
        found.from_cells += out.from_cells
    write_pages(root, document, found)
    return found


def write_pages(root: Path, document: Path, found: Found) -> None:
    # When you write this, check the pages you wrote with kdb_tools.validate.validate(root, pages=...) and
    # kdb_tools.ground.ground(root, pages=...): the ar4 profile's rules run with the core rules.
    raise NotImplementedError("writing kDB pages is yours: one page per part with its quantities, each citing a "
                              "source on that page (a quote with its bbox from kdb_tools.locate.find_quote, or a "
                              "spreadsheet cell), highlights, index.md and log.md")
