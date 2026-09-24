from config import Settings


def test_codecraft_environment_aliases_use_normal_openai_fields(monkeypatch):
    monkeypatch.setenv("CODECRAFT_BASE_URL", "https://codecraftapi.com/v1")
    monkeypatch.setenv("CODECRAFT_API_KEY", "test-key")
    monkeypatch.setenv("CODECRAFT_MODEL", "codecraft/gpt-5.6-sol")

    settings = Settings()

    assert settings.openai_base_url == "https://codecraftapi.com/v1"
    assert settings.openai_api_key == "test-key"
    assert settings.llm_model == settings.heavy_llm_model == "codecraft/gpt-5.6-sol"
