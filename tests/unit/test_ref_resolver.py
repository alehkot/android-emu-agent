"""Tests for ref resolver."""

from __future__ import annotations

from android_emu_agent.ui.ref_resolver import RefResolver


class TestRefResolver:
    """Tests for RefResolver."""

    def test_store_and_resolve_ref(self) -> None:
        """Should store and resolve refs correctly."""
        resolver = RefResolver()

        elements = [
            {
                "ref": "^a1",
                "resource_id": "com.test:id/button",
                "content_desc": "Submit",
                "text": "Submit",
                "class": "Button",
                "bounds": [100, 200, 300, 250],
            },
        ]

        resolver.store_refs("s-1", generation=1, elements=elements)
        bundle, is_stale = resolver.resolve_ref("s-1", "^a1", current_generation=1)

        assert bundle is not None
        assert bundle.ref == "^a1"
        assert bundle.resource_id == "com.test:id/button"
        assert is_stale is False

    def test_resolve_stale_ref(self) -> None:
        """Should mark refs from old generations as stale."""
        resolver = RefResolver()

        elements = [{"ref": "^a1", "class": "Button", "bounds": [0, 0, 100, 100]}]
        resolver.store_refs("s-1", generation=1, elements=elements)

        bundle, is_stale = resolver.resolve_ref("s-1", "^a1", current_generation=5)

        assert bundle is not None
        assert is_stale is True

    def test_resolve_missing_ref(self) -> None:
        """Should return None for missing refs."""
        resolver = RefResolver()

        bundle, is_stale = resolver.resolve_ref("s-1", "^a99", current_generation=1)

        assert bundle is None
        assert is_stale is False

    def test_cleanup_old_generations(self) -> None:
        """Should cleanup generations older than current - 2."""
        resolver = RefResolver()

        # Store refs for multiple generations
        for gen in range(1, 6):
            elements = [{"ref": f"^a{gen}", "class": "View", "bounds": [0, 0, 100, 100]}]
            resolver.store_refs("s-1", generation=gen, elements=elements)

        # After storing gen 5, gens 1 and 2 should be cleaned up
        bundle, _ = resolver.resolve_ref("s-1", "^a1", current_generation=5)
        assert bundle is None  # Gen 1 was cleaned up

        bundle, _ = resolver.resolve_ref("s-1", "^a3", current_generation=5)
        assert bundle is not None  # Gen 3 still exists

    def test_clear_session(self) -> None:
        """Should clear all refs for a session."""
        resolver = RefResolver()

        elements = [{"ref": "^a1", "class": "View", "bounds": [0, 0, 100, 100]}]
        resolver.store_refs("s-1", generation=1, elements=elements)

        resolver.clear_session("s-1")

        bundle, _ = resolver.resolve_ref("s-1", "^a1", current_generation=1)
        assert bundle is None

    def test_rebind_locator_uses_selector_chain_against_latest_generation(self) -> None:
        """Should rebind stale refs to a newer generation using stored selector chains."""
        resolver = RefResolver()

        resolver.store_refs(
            "s-1",
            generation=1,
            elements=[
                {
                    "ref": "^a1",
                    "label": "Settings",
                    "class": "android.widget.LinearLayout",
                    "bounds": [0, 100, 100, 160],
                    "index": 0,
                    "ancestry_path": "hierarchy/android.widget.FrameLayout/android.widget.LinearLayout",
                    "element_hash": "same-row",
                    "selector_chain": [
                        {"kind": "label", "value": "Settings"},
                        {"kind": "class_name", "value": "android.widget.LinearLayout"},
                    ],
                }
            ],
        )
        resolver.store_refs(
            "s-1",
            generation=2,
            elements=[
                {
                    "ref": "^a9",
                    "resource_id": "com.test:id/settings_row",
                    "label": "Settings",
                    "class": "android.widget.LinearLayout",
                    "bounds": [0, 300, 100, 360],
                    "index": 0,
                    "ancestry_path": "hierarchy/android.widget.FrameLayout/android.widget.LinearLayout",
                    "element_hash": "same-row",
                    "selector_chain": [
                        {"kind": "resource_id", "value": "com.test:id/settings_row"},
                        {"kind": "label", "value": "Settings"},
                    ],
                }
            ],
        )

        stale_locator, is_stale = resolver.resolve_ref("s-1", "^a1", current_generation=2)

        assert stale_locator is not None
        assert is_stale is True

        rebound = resolver.rebind_locator("s-1", stale_locator, current_generation=2)

        assert rebound is not None
        assert rebound.ref == "^a9"
        assert rebound.resource_id == "com.test:id/settings_row"

    def test_rebind_locator_normalizes_compose_test_tag_resource_ids(self) -> None:
        """Compose test tags should match whether or not a package prefix is present."""
        resolver = RefResolver()

        resolver.store_refs(
            "s-1",
            generation=1,
            elements=[
                {
                    "ref": "^a1",
                    "resource_id": "compose_login_button",
                    "role": "clickable",
                    "state": {"clickable": True},
                    "class": "android.view.View",
                    "bounds": [0, 0, 100, 100],
                }
            ],
        )
        resolver.store_refs(
            "s-1",
            generation=2,
            elements=[
                {
                    "ref": "^a4",
                    "resource_id": "com.example:id/compose_login_button",
                    "role": "clickable",
                    "state": {"clickable": True},
                    "class": "android.view.View",
                    "bounds": [20, 20, 120, 120],
                }
            ],
        )

        stale_locator, is_stale = resolver.resolve_ref("s-1", "^a1", current_generation=2)

        assert stale_locator is not None
        assert is_stale is True

        rebound = resolver.rebind_locator("s-1", stale_locator, current_generation=2)

        assert rebound is not None
        assert rebound.ref == "^a4"
        assert rebound.resource_id == "com.example:id/compose_login_button"


class TestLocatorBundle:
    """Tests for LocatorBundle creation."""

    def test_ancestry_hash_computed(self) -> None:
        """Should compute ancestry hash from element properties."""
        resolver = RefResolver()

        elements = [
            {
                "ref": "^a1",
                "resource_id": "com.test:id/btn",
                "class": "Button",
                "bounds": [100, 200, 300, 250],
            },
        ]

        resolver.store_refs("s-1", generation=1, elements=elements)
        bundle, _ = resolver.resolve_ref("s-1", "^a1", current_generation=1)

        assert bundle is not None
        assert len(bundle.ancestry_hash) == 8  # MD5 truncated to 8 chars

    def test_bundle_to_dict(self) -> None:
        """Should convert bundle to dict for storage."""
        resolver = RefResolver()

        elements = [
            {
                "ref": "^a1",
                "resource_id": "com.test:id/btn",
                "content_desc": "Submit button",
                "text": "Submit",
                "class": "Button",
                "bounds": [100, 200, 300, 250],
            },
        ]

        resolver.store_refs("s-1", generation=1, elements=elements)
        bundle, _ = resolver.resolve_ref("s-1", "^a1", current_generation=1)

        assert bundle is not None
        result = bundle.to_dict()

        assert result["ref"] == "^a1"
        assert result["generation"] == 1
        assert result["resource_id"] == "com.test:id/btn"
        assert result["bounds"] == [100, 200, 300, 250]

    def test_locator_bundle_has_ancestry_path(self) -> None:
        """Should have ancestry_path and element_hash fields with defaults."""
        resolver = RefResolver()

        elements = [
            {
                "ref": "^a1",
                "resource_id": "com.test:id/btn",
                "class": "Button",
                "bounds": [100, 200, 300, 250],
            },
        ]

        resolver.store_refs("s-1", generation=1, elements=elements)
        bundle, _ = resolver.resolve_ref("s-1", "^a1", current_generation=1)

        assert bundle is not None
        # New fields should exist with default empty string values
        assert hasattr(bundle, "ancestry_path")
        assert hasattr(bundle, "element_hash")
        assert bundle.ancestry_path == ""
        assert bundle.element_hash == ""

    def test_to_dict_includes_new_fields(self) -> None:
        """Should include ancestry_path and element_hash in to_dict output."""
        resolver = RefResolver()

        elements = [
            {
                "ref": "^a1",
                "resource_id": "com.test:id/btn",
                "content_desc": "Submit button",
                "text": "Submit",
                "class": "Button",
                "bounds": [100, 200, 300, 250],
            },
        ]

        resolver.store_refs("s-1", generation=1, elements=elements)
        bundle, _ = resolver.resolve_ref("s-1", "^a1", current_generation=1)

        assert bundle is not None
        result = bundle.to_dict()

        # New fields must be in the dict
        assert "ancestry_path" in result
        assert "element_hash" in result
        assert result["ancestry_path"] == ""
        assert result["element_hash"] == ""
