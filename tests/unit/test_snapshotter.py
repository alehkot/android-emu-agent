"""Tests for UI snapshotter."""

from __future__ import annotations

from typing import Any

from android_emu_agent.ui.snapshotter import UISnapshotter


class TestUISnapshotter:
    """Tests for UISnapshotter."""

    def test_parse_hierarchy_extracts_interactive_elements(
        self,
        sample_hierarchy_xml: bytes,
        sample_device_info: dict[str, Any],
        sample_context_info: dict[str, Any],
    ) -> None:
        """Should extract only interactive elements."""
        snapshotter = UISnapshotter()
        snapshot = snapshotter.parse_hierarchy(
            xml_content=sample_hierarchy_xml,
            session_id="s-test",
            generation=1,
            device_info=sample_device_info,
            context_info=sample_context_info,
        )

        # Should have 4 interactive elements (button, text with content, edittext, checkbox)
        # Note: TextView with text is included due to string-length(@text)>0
        assert len(snapshot.elements) >= 3

        # Check refs are assigned
        refs = [e.ref for e in snapshot.elements]
        assert "^a1" in refs
        assert "^a2" in refs

    def test_parse_hierarchy_assigns_correct_roles(
        self,
        sample_hierarchy_xml: bytes,
        sample_device_info: dict[str, Any],
        sample_context_info: dict[str, Any],
    ) -> None:
        """Should infer correct roles from class names."""
        snapshotter = UISnapshotter()
        snapshot = snapshotter.parse_hierarchy(
            xml_content=sample_hierarchy_xml,
            session_id="s-test",
            generation=1,
            device_info=sample_device_info,
            context_info=sample_context_info,
        )

        roles = {e.role for e in snapshot.elements}
        assert "button" in roles
        assert "textfield" in roles
        assert "checkbox" in roles

    def test_parse_bounds(self) -> None:
        """Should correctly parse bounds string."""
        snapshotter = UISnapshotter()
        bounds = snapshotter._parse_bounds("[100,200][300,400]")
        assert bounds == [100, 200, 300, 400]

    def test_parse_bounds_invalid(self) -> None:
        """Should return zeros for invalid bounds."""
        snapshotter = UISnapshotter()
        bounds = snapshotter._parse_bounds("invalid")
        assert bounds == [0, 0, 0, 0]

    def test_snapshot_to_dict(
        self,
        sample_hierarchy_xml: bytes,
        sample_device_info: dict[str, Any],
        sample_context_info: dict[str, Any],
    ) -> None:
        """Should convert snapshot to JSON-serializable dict."""
        snapshotter = UISnapshotter()
        snapshot = snapshotter.parse_hierarchy(
            xml_content=sample_hierarchy_xml,
            session_id="s-test",
            generation=1,
            device_info=sample_device_info,
            context_info=sample_context_info,
        )

        result = snapshot.to_dict()

        assert result["schema_version"] == 1
        assert result["session_id"] == "s-test"
        assert result["generation"] == 1
        assert "elements" in result
        assert len(result["elements"]) > 0


class TestInteractiveFilter:
    """Tests for interactive element filtering."""

    def test_includes_clickable_elements(self) -> None:
        """Should include clickable elements."""
        xml = b"""<hierarchy>
            <node class="View" clickable="true" bounds="[0,0][100,100]"/>
        </hierarchy>"""

        snapshotter = UISnapshotter()
        snapshot = snapshotter.parse_hierarchy(xml, "s-1", 1, {}, {})

        assert len(snapshot.elements) == 1

    def test_includes_focusable_elements(self) -> None:
        """Should include focusable elements."""
        xml = b"""<hierarchy>
            <node class="View" focusable="true" bounds="[0,0][100,100]"/>
        </hierarchy>"""

        snapshotter = UISnapshotter()
        snapshot = snapshotter.parse_hierarchy(xml, "s-1", 1, {}, {})

        assert len(snapshot.elements) == 1

    def test_includes_elements_with_text(self) -> None:
        """Should include elements with text content."""
        xml = b"""<hierarchy>
            <node class="TextView" text="Hello" bounds="[0,0][100,100]"/>
        </hierarchy>"""

        snapshotter = UISnapshotter()
        snapshot = snapshotter.parse_hierarchy(xml, "s-1", 1, {}, {})

        assert len(snapshot.elements) == 1
        assert snapshot.elements[0].text == "Hello"

    def test_excludes_non_interactive_elements(self) -> None:
        """Should exclude non-interactive elements."""
        xml = b"""<hierarchy>
            <node class="FrameLayout" bounds="[0,0][100,100]"/>
        </hierarchy>"""

        snapshotter = UISnapshotter()
        snapshot = snapshotter.parse_hierarchy(xml, "s-1", 1, {}, {})

        assert len(snapshot.elements) == 0


class TestSnapshotSizeWarning:
    """Tests for snapshot size warning."""

    def test_no_warning_for_small_snapshot(self) -> None:
        """Should not include warnings for snapshots under 20KB."""
        xml = b"""<hierarchy>
            <node class="Button" clickable="true" bounds="[0,0][100,100]" text="Click"/>
        </hierarchy>"""

        snapshotter = UISnapshotter()
        snapshot = snapshotter.parse_hierarchy(xml, "s-1", 1, {}, {})
        result = snapshot.to_dict()

        assert "warnings" not in result

    def test_warning_for_large_snapshot(self) -> None:
        """Should include warning when snapshot exceeds 20KB."""
        # Build XML with 300 elements to exceed 20KB
        elements = []
        for i in range(300):
            elements.append(
                f'<node class="Button" clickable="true" bounds="[0,0][100,100]" '
                f'resource-id="com.example:id/button_{i}" '
                f'text="Button number {i} with some extra text to increase size" '
                f'content-desc="Description for button {i}"/>'
            )
        xml = f"<hierarchy>{''.join(elements)}</hierarchy>".encode()

        snapshotter = UISnapshotter()
        snapshot = snapshotter.parse_hierarchy(xml, "s-1", 1, {}, {})
        result = snapshot.to_dict()

        assert "warnings" in result
        assert len(result["warnings"]) == 1
        assert "exceeds 20KB" in result["warnings"][0]
