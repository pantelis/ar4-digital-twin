"""Host tests of twin-check's read binding that need no simulator."""
def test_a_root_relative_material_reference_binds_to_the_material_page(tmp_path):
    """links/<label>.md may name its material as /materials/x.md; the density read from that page is accepted."""
    from types import SimpleNamespace

    from twin_tools import check

    (tmp_path / "links").mkdir()
    (tmp_path / "materials").mkdir()
    (tmp_path / "links" / "link_1.md").write_text("---\ntype: Link\nmaterial: /materials/aluminum-6061.md\n---\n")
    (tmp_path / "materials" / "aluminum-6061.md").write_text("---\ntype: Material\n---\n")
    for ref in ("/materials/aluminum-6061.md", "../materials/aluminum-6061.md"):
        (tmp_path / "links" / "link_1.md").write_text(f"---\ntype: Link\nmaterial: {ref}\n---\n")
        test, _ = check._body_expects("link_1", "density", tmp_path)
        assert test(SimpleNamespace(page="materials/aluminum-6061.md", name="density")), ref
        assert not test(SimpleNamespace(page="materials/steel.md", name="density")), ref
