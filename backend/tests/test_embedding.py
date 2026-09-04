import asyncio
import json
import os
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services import embedding


class _StubEmbeddings:
    """Return vectors out of order so ordering by index is actually exercised."""

    def __init__(self, dimension: int = 3):
        self.dimension = dimension
        self.calls = []

    async def create(self, model, input):
        self.calls.append((model, list(input)))
        data = [
            SimpleNamespace(index=i, embedding=[float(i)] * self.dimension)
            for i in range(len(input))
        ]
        return SimpleNamespace(data=list(reversed(data)))


@pytest.fixture
def api_backend(tmp_path):
    """Pin the api backend with a stub client and an isolated cache file."""
    original = (
        settings.embedding_backend,
        settings.embedding_model,
        settings.embedding_api_key,
        settings.embedding_base_url,
        settings.llm_api_key,
        settings.llm_base_url,
        settings.embedding_cache_dir,
        embedding._api_client,
    )
    settings.embedding_backend = "api"
    settings.embedding_model = "stub-embedding-model"
    settings.embedding_api_key = "sk-stub"
    settings.embedding_cache_dir = str(tmp_path)
    stub = _StubEmbeddings()
    embedding._api_client = SimpleNamespace(embeddings=stub)
    yield stub
    (
        settings.embedding_backend,
        settings.embedding_model,
        settings.embedding_api_key,
        settings.embedding_base_url,
        settings.llm_api_key,
        settings.llm_base_url,
        settings.embedding_cache_dir,
        embedding._api_client,
    ) = original


def test_auto_backend_falls_back_to_api_without_sentence_transformers():
    """The packaged desktop sidecar can never gain the optional local package."""
    original = settings.embedding_backend
    settings.embedding_backend = "auto"
    try:
        import importlib.util

        expected = "local" if importlib.util.find_spec("sentence_transformers") else "api"
        assert embedding.resolve_backend() == expected
    finally:
        settings.embedding_backend = original


def test_backend_is_read_per_call_not_captured_at_import():
    original = settings.embedding_backend
    try:
        settings.embedding_backend = "local"
        assert embedding.resolve_backend() == "local"
        settings.embedding_backend = "  API  "
        assert embedding.resolve_backend() == "api"
        settings.embedding_backend = ""
        assert embedding.resolve_backend() in {"local", "api"}
    finally:
        settings.embedding_backend = original


def test_embed_batch_runs_inside_a_running_event_loop(api_backend):
    """Regression: the api backend used loop.run_until_complete from async callers.

    Both call sites (phase3.index_embeddings and
    LectureAgent._retrieve_relevant_chunks) are coroutines, so the old
    implementation always raised "This event loop is already running".
    """

    async def async_call_site():
        return await embedding.embed_batch(["alpha", "beta", "gamma"])

    vectors = asyncio.run(async_call_site())
    assert len(vectors) == 3
    assert vectors[0] == [0.0, 0.0, 0.0]
    assert vectors[2] == [2.0, 2.0, 2.0]
    assert api_backend.calls == [("stub-embedding-model", ["alpha", "beta", "gamma"])]


def test_embed_text_delegates_to_batch(api_backend):
    async def async_call_site():
        return await embedding.embed_text("solo")

    assert asyncio.run(async_call_site()) == [0.0, 0.0, 0.0]


def test_api_backend_without_any_key_names_the_setting(api_backend):
    embedding._api_client = None
    settings.embedding_api_key = ""
    settings.llm_api_key = ""

    async def async_call_site():
        return await embedding.embed_batch(["alpha"])

    with pytest.raises(RuntimeError) as error:
        asyncio.run(async_call_site())
    assert "EMBEDDING_API_KEY" in str(error.value)


def test_openai_endpoint_gets_a_default_model(api_backend):
    settings.embedding_model = ""
    settings.embedding_base_url = "https://api.openai.com/v1"
    assert embedding.resolve_api_model() == embedding.DEFAULT_API_MODEL


def test_non_openai_endpoint_requires_an_explicit_model(api_backend):
    """An OpenAI model name means nothing to another provider's endpoint."""
    settings.embedding_model = ""
    settings.embedding_base_url = "https://api.example-provider.cn/v1"
    with pytest.raises(RuntimeError) as error:
        embedding.resolve_api_model()
    message = str(error.value)
    assert "EMBEDDING_MODEL" in message
    assert "api.example-provider.cn" in message


def test_explicit_model_wins_for_any_endpoint(api_backend):
    settings.embedding_base_url = "https://api.example-provider.cn/v1"
    settings.embedding_model = "provider-embedding-v1"
    assert embedding.resolve_api_model() == "provider-embedding-v1"


def test_cache_reads_survive_an_unconfigured_model(api_backend):
    """Retrieval must still fall back to keywords instead of raising."""
    settings.embedding_model = ""
    settings.embedding_base_url = "https://api.example-provider.cn/v1"
    assert embedding.load_cache() == {}


def test_cosine_similarity_scores_zero_across_dimensions():
    """A cache entry from another backend must not abort the retrieval pass."""
    assert embedding.cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert embedding.cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0


def test_cache_is_ignored_when_the_producing_model_changes(api_backend):
    embedding.save_cache({"chunk-1": [1.0, 0.0, 0.0]})
    assert embedding.load_cache() == {"chunk-1": [1.0, 0.0, 0.0]}

    settings.embedding_model = "another-embedding-model"
    assert embedding.load_cache() == {}

    settings.embedding_model = "stub-embedding-model"
    assert embedding.load_cache() == {"chunk-1": [1.0, 0.0, 0.0]}


def test_untagged_legacy_cache_is_ignored(api_backend):
    with open(embedding.cache_file(), "w", encoding="utf-8") as handle:
        json.dump({"chunk-9": [0.1, 0.2]}, handle)
    assert embedding.load_cache() == {}


def test_unreadable_cache_does_not_raise(api_backend):
    with open(embedding.cache_file(), "w", encoding="utf-8") as handle:
        handle.write("{not json")
    assert embedding.load_cache() == {}


def test_cache_directory_follows_the_configured_override(tmp_path):
    """The desktop sidecar redirects this to per-user application data.

    A frozen onefile bundle unpacks next to the module into a temporary
    directory that is deleted on exit, so a module-relative cache would be
    discarded on every launch.
    """
    original = settings.embedding_cache_dir
    try:
        settings.embedding_cache_dir = str(tmp_path / "appdata-embeddings")
        assert embedding.cache_dir() == str(tmp_path / "appdata-embeddings")
        assert embedding.cache_file().startswith(str(tmp_path / "appdata-embeddings"))

        settings.embedding_cache_dir = ""
        assert embedding.cache_dir() == embedding.DEFAULT_CACHE_DIR
    finally:
        settings.embedding_cache_dir = original


def test_save_cache_creates_a_missing_directory(tmp_path):
    original = (settings.embedding_cache_dir, settings.embedding_backend)
    try:
        settings.embedding_backend = "api"
        settings.embedding_cache_dir = str(tmp_path / "nested" / "embeddings")
        embedding.save_cache({"chunk-1": [1.0]})
        assert embedding.load_cache() == {"chunk-1": [1.0]}
    finally:
        settings.embedding_cache_dir, settings.embedding_backend = original


def test_unknown_backend_value_resolves_consistently():
    """The runtime settings API accepts any string for EMBEDDING_BACKEND.

    An unrecognised value used to leak through: embed_batch treated anything
    that was not "api" as local, while _cache_identity treated anything that
    was not "local" as api, so the two disagreed about the same setting.
    """
    original = settings.embedding_backend
    try:
        settings.embedding_backend = "atuo"  # a plausible typo for "auto"
        resolved = embedding.resolve_backend()
        assert resolved in {"local", "api"}
        assert embedding._cache_identity()["backend"] == resolved
    finally:
        settings.embedding_backend = original


def test_endpoint_userinfo_is_redacted_before_logging():
    assert embedding.redacted_endpoint("https://user:pw@host.example/v1") == (
        "https://host.example/v1"
    )
    assert embedding.redacted_endpoint("https://host.example:8443/v1") == (
        "https://host.example:8443/v1"
    )
    assert embedding.redacted_endpoint("") == ""


def test_unconfigured_model_error_does_not_leak_credentials(api_backend):
    settings.embedding_model = ""
    settings.embedding_base_url = "https://user:supersecret@vectors.example.cn/v1"
    with pytest.raises(RuntimeError) as error:
        embedding.resolve_api_model()
    message = str(error.value)
    assert "supersecret" not in message
    assert "user:" not in message
    assert "vectors.example.cn" in message


def test_bulk_cache_write_touches_the_file_once(api_backend, monkeypatch):
    """Writing per chunk rewrote the whole document for every vector."""
    writes = {"count": 0}
    real_save = embedding.save_cache

    def counting_save(cache):
        writes["count"] += 1
        return real_save(cache)

    monkeypatch.setattr(embedding, "save_cache", counting_save)
    stored = embedding.cache_embeddings({1: [1.0], 2: [2.0], 3: [3.0]})

    assert stored == 3
    assert writes["count"] == 1
    monkeypatch.undo()
    assert embedding.load_cache() == {"chunk-1": [1.0], "chunk-2": [2.0], "chunk-3": [3.0]}


def test_bulk_cache_write_ignores_an_empty_mapping(api_backend):
    assert embedding.cache_embeddings({}) == 0


def test_save_cache_leaves_no_temporary_file(api_backend):
    embedding.save_cache({"chunk-1": [1.0]})
    leftovers = [name for name in os.listdir(embedding.cache_dir()) if name.endswith(".tmp")]
    assert leftovers == []
    assert embedding.load_cache() == {"chunk-1": [1.0]}


def test_redact_credentials_handles_urls_the_replace_approach_missed():
    """Provider errors embed the URL in shapes we do not control."""
    leaked = (
        "Error connecting to https://alice:hunter2@vectors.example.cn/v1/embeddings "
        "(retry at https://alice:hunter2@vectors.example.cn/v1/)"
    )
    cleaned = embedding.redact_credentials(leaked)
    assert "hunter2" not in cleaned
    assert "alice" not in cleaned
    assert "vectors.example.cn/v1/embeddings" in cleaned


def test_redact_credentials_leaves_ordinary_text_alone():
    assert embedding.redact_credentials("https://api.openai.com/v1") == (
        "https://api.openai.com/v1"
    )
    assert embedding.redact_credentials("ratio 3:4@ok") == "ratio 3:4@ok"
    assert embedding.redact_credentials(RuntimeError("plain failure")) == "plain failure"


def test_redaction_bounds_provider_errors_that_quote_submitted_text():
    """A provider 400 can quote the input, which is learner material."""
    leaked = (
        "BadRequestError: input too long at https://bob:pw123@vectors.example.cn/v1: "
        + "学员上传的讲义原文 " * 40
    )
    bounded = embedding.redact_credentials(leaked)[:150]
    assert "pw123" not in bounded
    assert len(bounded) <= 150
