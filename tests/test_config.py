from pathlib import Path
from engram.config import load_config

def test_default_vault_root(monkeypatch, tmp_path):
    monkeypatch.delenv("ENGRAM_VAULT_ROOT", raising=False)
    cfg = load_config(config_path=None, home=tmp_path)
    assert cfg.vault_root == tmp_path / ".engram" / "vault"

def test_env_overrides_vault_root(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGRAM_VAULT_ROOT", str(tmp_path / "myvault"))
    cfg = load_config(config_path=None, home=tmp_path)
    assert cfg.vault_root == tmp_path / "myvault"

def test_toml_sets_enabled_types(tmp_path):
    toml = tmp_path / "engram.toml"
    toml.write_text(
        '[vault]\nroot = "%s"\n[types]\nenabled = ["decision","bug"]\n'
        % (tmp_path / "v").as_posix()
    )
    cfg = load_config(config_path=toml, home=tmp_path)
    assert cfg.enabled_types == ["decision", "bug"]
    assert cfg.vault_root == tmp_path / "v"

def test_defaults_present(monkeypatch, tmp_path):
    monkeypatch.delenv("ENGRAM_VAULT_ROOT", raising=False)
    cfg = load_config(config_path=None, home=tmp_path)
    assert cfg.rate_calls == 30
    assert cfg.rate_window_seconds == 60
    assert cfg.lock_timeout_seconds == 5
    assert cfg.context_warning_pct == 35
    assert cfg.context_critical_pct == 50
    assert cfg.ollama_endpoint == "http://localhost:11434"
    assert cfg.embed_model == "bge-m3"
    assert cfg.synth_model == "qwen3:7b"
    assert cfg.synth_timeout_seconds == 120
    assert cfg.keep_alive == "30m"
    assert cfg.crosslink_threshold == 0.65
    assert "decision" in cfg.enabled_types


def test_synthesis_tuning_from_toml(tmp_path):
    toml = tmp_path / "engram.toml"
    toml.write_text(
        '[vault]\nroot = "%s"\n[synthesis]\nmodel = "qwen2.5-coder:7b"\n'
        'timeout_seconds = 200\nkeep_alive = "1h"\n'
        % (tmp_path / "v").as_posix()
    )
    cfg = load_config(config_path=toml, home=tmp_path)
    assert cfg.synth_model == "qwen2.5-coder:7b"
    assert cfg.synth_timeout_seconds == 200
    assert cfg.keep_alive == "1h"
