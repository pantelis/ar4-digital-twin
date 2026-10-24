"""Your AR4 twin. twin-check loads this file and calls build().

Add one link per rigid part, with the meshes you exported from FreeCAD into cad/, and one joint
per axis. Every mass, limit, effort limit and velocity limit should trace back to a source in your kDB.
"""

import newton


def build(builder: newton.ModelBuilder) -> None:
    raise NotImplementedError("build the AR4 here: links from your meshes in cad/, joints from your kDB")
