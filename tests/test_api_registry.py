"""
API Registry Test Suite
========================
Tests for the API registry/marketplace layer: search, add, get, connect,
stats, remove, seed catalog, persistence, and blackbox bridge.
"""

import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_registry(tmp_path):
    """Redirect registry storage to a temp dir and reset module state."""
    import solstice_agent.tools.api_registry as mod

    # Reset module-level catalog
    mod._catalog = None

    # Redirect storage to tmp
    original_dir = mod._REGISTRY_DIR
    mod._REGISTRY_DIR = tmp_path / "registry"

    yield tmp_path / "registry"

    # Restore
    mod._REGISTRY_DIR = original_dir
    mod._catalog = None


# ---------------------------------------------------------------------------
# Seed Catalog
# ---------------------------------------------------------------------------

class TestSeedCatalog:

    def test_seed_catalog_file_exists(self):
        from solstice_agent.tools.api_registry import _SEED_CATALOG
        assert _SEED_CATALOG.exists(), "seed_catalog.json not found"

    def test_seed_catalog_valid_json(self):
        from solstice_agent.tools.api_registry import _SEED_CATALOG
        data = json.loads(_SEED_CATALOG.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert len(data) == 25

    def test_seed_catalog_required_fields(self):
        from solstice_agent.tools.api_registry import _SEED_CATALOG
        data = json.loads(_SEED_CATALOG.read_text(encoding="utf-8"))
        required = {"name", "url", "description", "category", "tags",
                    "auth_type", "pricing", "stats"}
        for name, entry in data.items():
            missing = required - set(entry.keys())
            assert not missing, f"API '{name}' missing fields: {missing}"

    def test_seed_catalog_urls_are_https(self):
        from solstice_agent.tools.api_registry import _SEED_CATALOG
        data = json.loads(_SEED_CATALOG.read_text(encoding="utf-8"))
        for name, entry in data.items():
            assert entry["url"].startswith("https://"), \
                f"API '{name}' URL not HTTPS: {entry['url']}"

    def test_seed_catalog_categories(self):
        from solstice_agent.tools.api_registry import _SEED_CATALOG
        data = json.loads(_SEED_CATALOG.read_text(encoding="utf-8"))
        categories = set(e["category"] for e in data.values())
        assert len(categories) >= 8, f"Only {len(categories)} categories: {categories}"

    def test_seed_catalog_auth_types_valid(self):
        from solstice_agent.tools.api_registry import _SEED_CATALOG
        data = json.loads(_SEED_CATALOG.read_text(encoding="utf-8"))
        valid = {"bearer", "basic", "api_key", "none"}
        for name, entry in data.items():
            assert entry["auth_type"] in valid, \
                f"API '{name}' invalid auth_type: {entry['auth_type']}"

    def test_seed_catalog_tags_are_lists(self):
        from solstice_agent.tools.api_registry import _SEED_CATALOG
        data = json.loads(_SEED_CATALOG.read_text(encoding="utf-8"))
        for name, entry in data.items():
            assert isinstance(entry["tags"], list), f"API '{name}' tags not a list"
            assert len(entry["tags"]) >= 2, f"API '{name}' has <2 tags"

    def test_seed_catalog_no_tokens_prefilled(self):
        from solstice_agent.tools.api_registry import _SEED_CATALOG
        data = json.loads(_SEED_CATALOG.read_text(encoding="utf-8"))
        for name, entry in data.items():
            assert entry.get("auth_token", "") == "", \
                f"API '{name}' has a pre-filled auth_token!"


# ---------------------------------------------------------------------------
# Catalog Loading & Persistence
# ---------------------------------------------------------------------------

class TestCatalogLoading:

    def test_first_run_seeds_catalog(self, isolated_registry):
        from solstice_agent.tools.api_registry import _load_catalog
        catalog = _load_catalog()
        assert len(catalog) == 25
        assert "twilio" in catalog
        assert "stripe" in catalog

    def test_catalog_persists_to_disk(self, isolated_registry):
        from solstice_agent.tools.api_registry import _load_catalog, _save_catalog
        catalog = _load_catalog()
        catalog["test_api"] = {"name": "test_api", "url": "https://test.com"}
        _save_catalog()

        catalog_file = isolated_registry / "catalog.json"
        assert catalog_file.exists()
        on_disk = json.loads(catalog_file.read_text(encoding="utf-8"))
        assert "test_api" in on_disk

    def test_reload_from_disk(self, isolated_registry):
        import solstice_agent.tools.api_registry as mod
        catalog = mod._load_catalog()
        catalog["persisted"] = {"name": "persisted", "url": "https://x.com"}
        mod._save_catalog()

        # Reset in-memory state
        mod._catalog = None
        reloaded = mod._load_catalog()
        assert "persisted" in reloaded

    def test_empty_catalog_if_no_seed(self, isolated_registry):
        import solstice_agent.tools.api_registry as mod
        original_seed = mod._SEED_CATALOG
        mod._SEED_CATALOG = Path("/nonexistent/seed.json")
        mod._catalog = None

        catalog = mod._load_catalog()
        assert catalog == {}

        mod._SEED_CATALOG = original_seed


# ---------------------------------------------------------------------------
# registry_search
# ---------------------------------------------------------------------------

class TestRegistrySearch:

    def test_search_by_tag(self):
        from solstice_agent.tools.api_registry import registry_search
        result = registry_search("sms")
        assert "twilio" in result.lower()

    def test_search_by_name(self):
        from solstice_agent.tools.api_registry import registry_search
        result = registry_search("stripe")
        assert "stripe" in result.lower()

    def test_search_by_description_word(self):
        from solstice_agent.tools.api_registry import registry_search
        result = registry_search("weather")
        assert "openweathermap" in result.lower()
        assert "weatherapi" in result.lower()

    def test_search_with_category_filter(self):
        from solstice_agent.tools.api_registry import registry_search
        result = registry_search("api", category="payments")
        assert "stripe" in result.lower() or "paypal" in result.lower()
        assert "twilio" not in result.lower()

    def test_search_category_mismatch(self):
        from solstice_agent.tools.api_registry import registry_search
        # Category that doesn't exist in seed catalog
        result = registry_search("sms", category="robotics")
        assert "No APIs match" in result

    def test_search_no_match(self):
        from solstice_agent.tools.api_registry import registry_search
        result = registry_search("xyznonexistent12345")
        assert "No APIs match" in result
        assert "categories" in result.lower()

    def test_search_returns_multiple(self):
        from solstice_agent.tools.api_registry import registry_search
        result = registry_search("ai")
        # Should find openai_api, anthropic_api, replicate, huggingface
        lines = result.strip().split("\n")
        # First line is summary, then pairs of lines per result
        assert "Found" in lines[0]

    def test_search_email(self):
        from solstice_agent.tools.api_registry import registry_search
        result = registry_search("email")
        assert "sendgrid" in result.lower() or "resend" in result.lower()

    def test_search_geocoding(self):
        from solstice_agent.tools.api_registry import registry_search
        result = registry_search("geocoding")
        assert "google_maps" in result.lower() or "mapbox" in result.lower()

    def test_search_empty_catalog(self, isolated_registry):
        import solstice_agent.tools.api_registry as mod
        mod._catalog = {}
        result = mod.registry_search("anything")
        assert "empty" in result.lower()


# ---------------------------------------------------------------------------
# registry_add
# ---------------------------------------------------------------------------

class TestRegistryAdd:

    def test_add_basic(self):
        from solstice_agent.tools.api_registry import registry_add, registry_get
        result = registry_add(
            "test_api", "https://api.test.com", "A test API",
            "testing", "test, demo"
        )
        assert "Registered" in result
        assert "test_api" in result

        detail = registry_get("test_api")
        assert "https://api.test.com" in detail

    def test_add_with_auth(self):
        from solstice_agent.tools.api_registry import registry_add, _load_catalog
        registry_add(
            "auth_api", "https://api.auth.com", "Authed API",
            "testing", "test", auth_type="bearer", auth_token="sk-xxx"
        )
        catalog = _load_catalog()
        assert catalog["auth_api"]["auth_type"] == "bearer"
        assert catalog["auth_api"]["auth_token"] == "sk-xxx"

    def test_add_with_pricing(self):
        from solstice_agent.tools.api_registry import registry_add, _load_catalog
        registry_add(
            "paid_api", "https://api.paid.com", "Paid API",
            "testing", "test", pricing="pay-per-use"
        )
        catalog = _load_catalog()
        assert catalog["paid_api"]["pricing"] == "pay-per-use"

    def test_add_duplicate_rejected(self):
        from solstice_agent.tools.api_registry import registry_add
        registry_add("dup_api", "https://dup.com", "First", "test", "a")
        result = registry_add("dup_api", "https://dup2.com", "Second", "test", "b")
        assert "already exists" in result

    def test_add_invalid_auth_type(self):
        from solstice_agent.tools.api_registry import registry_add
        result = registry_add(
            "bad_auth", "https://bad.com", "Bad", "test", "a",
            auth_type="oauth"
        )
        assert "Invalid auth_type" in result

    def test_add_normalizes_name(self):
        from solstice_agent.tools.api_registry import registry_add, _load_catalog
        registry_add("My Cool API", "https://cool.com", "Cool", "test", "a")
        catalog = _load_catalog()
        assert "my_cool_api" in catalog

    def test_add_normalizes_tags(self):
        from solstice_agent.tools.api_registry import registry_add, _load_catalog
        registry_add("tag_test", "https://tag.com", "Tags", "test", "  FOO , Bar ,baz  ")
        catalog = _load_catalog()
        assert catalog["tag_test"]["tags"] == ["foo", "bar", "baz"]

    def test_add_sets_timestamps(self):
        from solstice_agent.tools.api_registry import registry_add, _load_catalog
        registry_add("ts_api", "https://ts.com", "Timestamps", "test", "a")
        catalog = _load_catalog()
        assert catalog["ts_api"]["added_at"] is not None
        assert catalog["ts_api"]["last_used"] is None

    def test_add_initializes_stats(self):
        from solstice_agent.tools.api_registry import registry_add, _load_catalog
        registry_add("stats_api", "https://stats.com", "Stats", "test", "a")
        catalog = _load_catalog()
        stats = catalog["stats_api"]["stats"]
        assert stats["total_calls"] == 0
        assert stats["success_rate"] is None
        assert stats["avg_latency_ms"] is None

    def test_add_strips_trailing_slash(self):
        from solstice_agent.tools.api_registry import registry_add, _load_catalog
        registry_add("slash_api", "https://slash.com/v1/", "Slash", "test", "a")
        catalog = _load_catalog()
        assert catalog["slash_api"]["url"] == "https://slash.com/v1"


# ---------------------------------------------------------------------------
# registry_get
# ---------------------------------------------------------------------------

class TestRegistryGet:

    def test_get_existing(self):
        from solstice_agent.tools.api_registry import registry_get
        result = registry_get("twilio")
        assert "twilio" in result.lower()
        assert "https://api.twilio.com" in result
        assert "sms" in result.lower()

    def test_get_not_found(self):
        from solstice_agent.tools.api_registry import registry_get
        result = registry_get("nonexistent_api_xyz")
        assert "not found" in result.lower()

    def test_get_fuzzy_suggestion(self):
        from solstice_agent.tools.api_registry import registry_get
        result = registry_get("twil")  # partial match
        assert "did you mean" in result.lower()
        assert "twilio" in result.lower()

    def test_get_shows_all_fields(self):
        from solstice_agent.tools.api_registry import registry_get
        result = registry_get("stripe")
        assert "URL:" in result
        assert "Description:" in result
        assert "Category:" in result
        assert "Tags:" in result
        assert "Auth:" in result
        assert "Pricing:" in result
        assert "Stats:" in result


# ---------------------------------------------------------------------------
# registry_remove
# ---------------------------------------------------------------------------

class TestRegistryRemove:

    def test_remove_existing(self):
        from solstice_agent.tools.api_registry import registry_remove, _load_catalog
        catalog = _load_catalog()
        assert "twilio" in catalog

        result = registry_remove("twilio")
        assert "Removed" in result
        assert "twilio" not in _load_catalog()

    def test_remove_not_found(self):
        from solstice_agent.tools.api_registry import registry_remove
        result = registry_remove("nonexistent_xyz")
        assert "not found" in result.lower()

    def test_remove_then_search(self):
        from solstice_agent.tools.api_registry import registry_remove, registry_search
        registry_remove("twilio")
        result = registry_search("sms")
        assert "twilio" not in result.lower()


# ---------------------------------------------------------------------------
# registry_stats
# ---------------------------------------------------------------------------

class TestRegistryStats:

    def test_stats_no_usage(self):
        from solstice_agent.tools.api_registry import registry_stats
        result = registry_stats("twilio")
        assert "No usage data" in result

    def test_stats_not_found(self):
        from solstice_agent.tools.api_registry import registry_stats
        result = registry_stats("nonexistent_xyz")
        assert "not found" in result.lower()

    def test_stats_with_data(self):
        from solstice_agent.tools.api_registry import registry_stats, _load_catalog
        catalog = _load_catalog()
        catalog["twilio"]["stats"] = {
            "total_calls": 50,
            "success_rate": 0.96,
            "avg_latency_ms": 150,
            "last_checked": "2026-02-18T00:00:00+00:00",
        }
        result = registry_stats("twilio")
        assert "50" in result
        assert "96" in result
        assert "150ms" in result
        assert "EXCELLENT" in result
        assert "FAST" in result

    def test_stats_degraded_health(self):
        from solstice_agent.tools.api_registry import registry_stats, _load_catalog
        catalog = _load_catalog()
        catalog["stripe"]["stats"] = {
            "total_calls": 100,
            "success_rate": 0.65,
            "avg_latency_ms": 1500,
            "last_checked": "2026-02-18T00:00:00+00:00",
        }
        result = registry_stats("stripe")
        assert "DEGRADED" in result
        assert "SLOW" in result

    def test_stats_poor_health(self):
        from solstice_agent.tools.api_registry import registry_stats, _load_catalog
        catalog = _load_catalog()
        catalog["paypal"]["stats"] = {
            "total_calls": 20,
            "success_rate": 0.30,
            "avg_latency_ms": 500,
            "last_checked": "2026-02-18T00:00:00+00:00",
        }
        result = registry_stats("paypal")
        assert "POOR" in result


# ---------------------------------------------------------------------------
# registry_connect (Blackbox bridge)
# ---------------------------------------------------------------------------

class TestRegistryConnect:

    def test_connect_not_found(self):
        from solstice_agent.tools.api_registry import registry_connect
        result = registry_connect("nonexistent_xyz")
        assert "not found" in result.lower()

    def test_connect_fuzzy_suggestion(self):
        from solstice_agent.tools.api_registry import registry_connect
        result = registry_connect("twil")
        assert "did you mean" in result.lower()

    def test_connect_calls_blackbox(self):
        """Verify registry_connect calls blackbox_connect with correct args."""
        mock_connect = MagicMock(return_value="Connected to https://api.twilio.com. Status: 200. Mode: read-only. TLS verified.")
        mock_discover = MagicMock(return_value="Endpoints: 15")

        with patch("solstice_agent.tools.blackbox.blackbox_connect", mock_connect), \
             patch("solstice_agent.tools.blackbox.blackbox_discover", mock_discover):
            from solstice_agent.tools.api_registry import registry_connect, _load_catalog

            catalog = _load_catalog()
            catalog["twilio"]["auth_token"] = "test-token-123"

            registry_connect("twilio")

        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args
        assert call_kwargs[1]["url"] == "https://api.twilio.com"
        assert call_kwargs[1]["auth_token"] == "test-token-123"
        assert call_kwargs[1]["allow_write"] is False

    def test_connect_updates_stats_on_success(self):
        mock_connect = MagicMock(return_value="Connected to https://jsonplaceholder.typicode.com. Status: 200.")
        mock_discover = MagicMock(return_value="Endpoints: 6")

        with patch("solstice_agent.tools.blackbox.blackbox_connect", mock_connect), \
             patch("solstice_agent.tools.blackbox.blackbox_discover", mock_discover):
            from solstice_agent.tools.api_registry import registry_connect, _load_catalog
            registry_connect("jsonplaceholder")

        catalog = _load_catalog()
        stats = catalog["jsonplaceholder"]["stats"]
        assert stats["total_calls"] == 1
        assert stats["success_rate"] is not None
        assert stats["avg_latency_ms"] is not None
        assert catalog["jsonplaceholder"]["last_used"] is not None
        assert catalog["jsonplaceholder"]["endpoints_discovered"] == 6

    def test_connect_updates_stats_on_failure(self):
        mock_connect = MagicMock(return_value="Error: Connection refused")
        mock_discover = MagicMock(return_value="")

        with patch("solstice_agent.tools.blackbox.blackbox_connect", mock_connect), \
             patch("solstice_agent.tools.blackbox.blackbox_discover", mock_discover):
            from solstice_agent.tools.api_registry import registry_connect, _load_catalog
            result = registry_connect("jsonplaceholder")

        assert "failure" in result.lower()
        catalog = _load_catalog()
        stats = catalog["jsonplaceholder"]["stats"]
        assert stats["total_calls"] == 1
        assert stats["success_rate"] == 0.0

    def test_connect_no_auth_for_none_type(self):
        mock_connect = MagicMock(return_value="Connected to https://restcountries.com/v3.1. Status: 200.")
        mock_discover = MagicMock(return_value="")

        with patch("solstice_agent.tools.blackbox.blackbox_connect", mock_connect), \
             patch("solstice_agent.tools.blackbox.blackbox_discover", mock_discover):
            from solstice_agent.tools.api_registry import registry_connect
            registry_connect("restcountries")

        call_kwargs = mock_connect.call_args
        assert call_kwargs[1]["auth_token"] is None


# ---------------------------------------------------------------------------
# Scoring / Search ranking
# ---------------------------------------------------------------------------

class TestSearchScoring:

    def test_exact_name_ranks_highest(self):
        from solstice_agent.tools.api_registry import _score_match
        entry = {"name": "twilio", "description": "SMS API", "tags": ["sms"], "category": "comm"}
        score = _score_match(entry, "twilio")
        assert score >= 100  # exact name match

    def test_tag_match_scores_well(self):
        from solstice_agent.tools.api_registry import _score_match
        entry = {"name": "twilio", "description": "API", "tags": ["sms", "voice"], "category": "comm"}
        score = _score_match(entry, "sms")
        assert score >= 40

    def test_description_match(self):
        from solstice_agent.tools.api_registry import _score_match
        entry = {"name": "x", "description": "payment processing system", "tags": [], "category": "pay"}
        score = _score_match(entry, "payment")
        assert score > 0

    def test_category_filter_zeroes_mismatch(self):
        from solstice_agent.tools.api_registry import _score_match
        entry = {"name": "twilio", "description": "SMS", "tags": ["sms"], "category": "communication"}
        score = _score_match(entry, "sms", category="weather")
        assert score == 0

    def test_category_filter_boosts_match(self):
        from solstice_agent.tools.api_registry import _score_match
        entry = {"name": "twilio", "description": "SMS", "tags": ["sms"], "category": "communication"}
        without = _score_match(entry, "sms")
        with_cat = _score_match(entry, "sms", category="communication")
        assert with_cat > without

    def test_no_match_returns_zero(self):
        from solstice_agent.tools.api_registry import _score_match
        entry = {"name": "stripe", "description": "payments", "tags": ["pay"], "category": "payments"}
        score = _score_match(entry, "xyznonexistent")
        assert score == 0


# ---------------------------------------------------------------------------
# Integration: load_builtins with enable_registry
# ---------------------------------------------------------------------------

class TestRegistryIntegration:

    def test_load_builtins_includes_registry(self):
        from solstice_agent.tools.registry import ToolRegistry
        r = ToolRegistry()
        r.load_builtins()
        tools = r.list_tools()
        for name in ["registry_search", "registry_add", "registry_get",
                      "registry_connect", "registry_stats", "registry_remove"]:
            assert name in tools, f"{name} not in tools"

    def test_load_builtins_disable_registry(self):
        from solstice_agent.tools.registry import ToolRegistry
        r = ToolRegistry()
        r.load_builtins(enable_registry=False)
        tools = r.list_tools()
        assert "registry_search" not in tools
        assert "registry_add" not in tools

    def test_config_has_enable_registry(self):
        from solstice_agent.config import Config
        config = Config()
        assert hasattr(config, "enable_registry")
        assert config.enable_registry is True


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

class TestSchemas:

    def test_all_schemas_have_required_fields(self):
        from solstice_agent.tools.api_registry import _SCHEMAS
        assert len(_SCHEMAS) == 6
        for name, schema in _SCHEMAS.items():
            assert "name" in schema, f"Schema {name} missing 'name'"
            assert schema["name"] == name
            assert "description" in schema, f"Schema {name} missing 'description'"
            assert "parameters" in schema, f"Schema {name} missing 'parameters'"
            params = schema["parameters"]
            assert params["type"] == "object"
            assert "properties" in params
            assert "required" in params

    def test_schema_names_match_functions(self):
        from solstice_agent.tools import api_registry
        from solstice_agent.tools.api_registry import _SCHEMAS
        for name in _SCHEMAS:
            assert hasattr(api_registry, name), f"Function {name} not found"
            fn = getattr(api_registry, name)
            assert callable(fn), f"{name} is not callable"

    def test_schemas_match_registered_count(self):
        from solstice_agent.tools.registry import ToolRegistry
        r = ToolRegistry()
        r.load_builtins(
            enable_terminal=False, enable_web=False, enable_blackbox=False,
            enable_browser=False, enable_voice=False, enable_memory=False,
            enable_skills=False, enable_cron=False, enable_registry=True,
        )
        # file_ops always load + 6 registry
        registry_tools = [t for t in r.list_tools() if t.startswith("registry_")]
        assert len(registry_tools) == 6


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_add_and_search_roundtrip(self):
        from solstice_agent.tools.api_registry import registry_add, registry_search
        registry_add("custom_sms", "https://sms.custom.com", "Custom SMS service",
                      "communication", "sms, text, messaging")
        result = registry_search("sms")
        assert "custom_sms" in result.lower()

    def test_add_remove_add_again(self):
        from solstice_agent.tools.api_registry import registry_add, registry_remove
        registry_add("temp", "https://temp.com", "Temp", "test", "a")
        registry_remove("temp")
        result = registry_add("temp", "https://temp2.com", "Temp v2", "test", "b")
        assert "Registered" in result

    def test_search_case_insensitive(self):
        from solstice_agent.tools.api_registry import registry_search
        r1 = registry_search("SMS")
        r2 = registry_search("sms")
        # Both should find twilio
        assert "twilio" in r1.lower()
        assert "twilio" in r2.lower()

    def test_get_case_insensitive(self):
        from solstice_agent.tools.api_registry import registry_get
        r1 = registry_get("TWILIO")
        r2 = registry_get("twilio")
        assert "https://api.twilio.com" in r1
        assert "https://api.twilio.com" in r2

    def test_format_helpers(self):
        from solstice_agent.tools.api_registry import _fmt_pct, _fmt_ms
        assert _fmt_pct(0.956) == "95.6%"
        assert _fmt_pct(None) == "n/a"
        assert _fmt_ms(150.4) == "150ms"
        assert _fmt_ms(None) == "n/a"

    def test_concurrent_add_different_names(self):
        from solstice_agent.tools.api_registry import registry_add, _load_catalog
        for i in range(10):
            registry_add(f"api_{i}", f"https://api{i}.com", f"API {i}", "test", f"tag{i}")
        catalog = _load_catalog()
        for i in range(10):
            assert f"api_{i}" in catalog
