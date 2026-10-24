"""One link whose box takes Newton's default density (1000 kg/m^3); its joint values come from the kDB."""
import newton
from twin_tools.kdb import si


def build(builder: newton.ModelBuilder) -> None:
    upper = builder.add_link(label="upper_arm")
    builder.add_shape_box(upper, hx=0.15, hy=0.03, hz=0.01)
    page = "joints/j2.md"
    j2 = builder.add_joint_revolute(-1, upper, axis=(0.0, 1.0, 0.0), label="J2",
                                    limit_lower=si(page, "lower_limit"), limit_upper=si(page, "upper_limit"),
                                    effort_limit=si(page, "effort_limit"), velocity_limit=si(page, "velocity_limit"))
    builder.add_articulation([j2])
