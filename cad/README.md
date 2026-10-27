# CAD

One FreeCAD document per link, with the mesh your agent exported from it, for example
`base.FCStd` and `base.stl`. Keep the link's dimensions in a spreadsheet inside the document, so
that changing a value in your kDB rebuilds the part.

Name each document after its link page: `link-2.FCStd` and `link-2.stl` for `kdb/links/link-2.md`.
The spreadsheet is labeled `kDB`, with the quantity's reference in column A, the value and an alias
in column B and the unit in column C. Bind sketch dimensions and pad lengths to the aliases. Put the
document's origin at the link's DH frame. `docker/run.sh twin-sync` reports any drift from the kDB;
see "Keeping FreeCAD in sync" in the main README.
