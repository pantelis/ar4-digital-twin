"""sync.gui (twin_tools.guicheck): a FreeCAD document must be saved once with the GUI (twin-guisave). Pure zip and XML, so these run on
the host; test_sync.py checks the rule on documents FreeCAD writes."""
import zipfile

from twin_tools import guicheck
from twin_tools.check import Report

JOINT = '''<Object name="{name}"><Properties><Property name="Proxy" type="App::PropertyPythonObject">
<Python value="bnVsbA==" encoded="yes" module="JointObject" class="{cls}"/></Property></Properties></Object>'''
VIEW = '''<ViewProvider name="{name}"><Properties><Property name="Proxy" type="App::PropertyPythonObject">
<Python value="bnVsbA==" encoded="yes" module="JointObject" class="{cls}"/></Property>
<Property name="Visibility" type="App::PropertyBool"><Bool value="{visible}"/></Property></Properties></ViewProvider>'''


def fcstd(path, joints=(), views=None):
    """A minimal .FCStd: Document.xml with these (name, class) joints, and GuiDocument.xml with these
    (name, class, visible) view providers unless views is None."""
    objects = "".join(JOINT.format(name=n, cls=c) for n, c in joints)
    asm = '<Object type="Assembly::AssemblyObject" name="Assembly"/>' if joints else ""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Document.xml", f'<Document><Objects>{asm}</Objects><ObjectData>{objects}</ObjectData></Document>')
        if views is not None:
            body = "".join(VIEW.format(name=n, cls=c, visible=str(v).lower()) for n, c, v in views)
            z.writestr("GuiDocument.xml", f'<Document><ViewProviderData>{body}</ViewProviderData></Document>')
    return path


def rules(report):
    return [(f.rule, f.message) for f in report.findings]


def check(path):
    report = Report(tool="twin-sync")
    guicheck.check(path, report)
    return rules(report)


def test_a_document_saved_without_the_gui_is_a_finding(tmp_path):
    (rule, message), = check(fcstd(tmp_path / "link-2.FCStd"))
    assert rule == "sync.gui" and "GuiDocument.xml" in message and "twin-guisave" in message


def test_a_part_saved_with_the_gui_has_no_finding(tmp_path):
    assert check(fcstd(tmp_path / "link-2.FCStd", views=[])) == []


def test_joints_without_their_view_providers_are_a_finding(tmp_path):
    path = fcstd(tmp_path / "ar4.FCStd", joints=[("J1", "Joint"), ("J2", "Joint"), ("Ground", "GroundedJoint")],
                 views=[("J1", "ViewProviderJoint", True)])
    (rule, message), = check(path)
    assert rule == "sync.gui" and "J2" in message and "Ground" in message and "J1" not in message.split(":")[-1]


def test_a_hidden_joint_is_a_finding(tmp_path):
    path = fcstd(tmp_path / "ar4.FCStd", joints=[("J1", "Joint")], views=[("J1", "ViewProviderJoint", False)])
    (rule, message), = check(path)
    assert rule == "sync.gui" and "J1" in message


def test_an_assembly_saved_with_the_gui_has_no_finding(tmp_path):
    path = fcstd(tmp_path / "ar4.FCStd", joints=[("J1", "Joint"), ("Ground", "GroundedJoint")],
                 views=[("J1", "ViewProviderJoint", True), ("Ground", "ViewProviderGroundedJoint", True)])
    assert check(path) == []


def test_documents_in_subfolders_are_checked(tmp_path):
    (tmp_path / "gripper").mkdir()
    fcstd(tmp_path / "link-2.FCStd", views=[])
    fcstd(tmp_path / "gripper" / "jaw1.FCStd")
    report = Report(tool="twin-sync")
    guicheck.check_all(tmp_path, report)
    assert [(f.rule, f.path) for f in report.findings] == [("sync.gui", str(tmp_path / "gripper" / "jaw1.FCStd"))]
