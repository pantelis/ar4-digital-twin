"""Your AR4 twin. twin-check loads this file and calls build().

Add one link per rigid part, with the meshes you exported from FreeCAD into cad/, and one joint
per axis. Read every mass, density, limit, effort limit and velocity limit from your kDB with
twin_tools.kdb.si, for example si("joints/j2.md", "upper_limit"); twin-check reports any value
typed in here instead.
"""

import newton
from twin_tools.kdb import si  # noqa: F401


def build(builder: newton.ModelBuilder) -> None:
    raise NotImplementedError("build the AR4 here: links from your meshes in cad/, joints from your kDB")
