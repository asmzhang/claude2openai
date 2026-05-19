from pathlib import Path
import subprocess
import sys

import pytest

import claude2openai_gateway.bootstrap as bootstrap
from claude2openai_gateway.bootstrap import (
    LaunchSpec,
    build_cc_switch_env,
    build_fixup_launch_spec,
    build_gateway_launch_spec,
    ensure_service_started,
    inspect_service,
    load_repo_config,
    normalize_cli_argv,
    resolve_backend_api_key,
)


def test_build_cc_switch_env_points_claude_at_local_gateway():
    assert build_cc_switch_env(
        gateway_url="http://127.0.0.1:4000",
        gateway_key="local-gateway-key",
        gateway_model="gpt-5.5",
    ) == {
        "ANTHROPIC_AUTH_TOKEN": "local-gateway-key",
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:4000",
        "ANTHROPIC_CUSTOM_MODEL_OPTION": "gpt-5.5",
        "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME": "gpt-5.5",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "gpt-5.5",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "gpt-5.5",
        "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME": "gpt-5.5",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "gpt-5.5",
        "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME": "gpt-5.5",
    }


def test_build_fixup_launch_spec_uses_backend_key_and_repo_src():
    spec = build_fixup_launch_spec(
        repo_root=Path("D:/4/claude2openai"),
        backend_base_url="http://127.0.0.1:8327/v1",
        backend_api_key="real-key",
        port=8328,
    )

    assert spec.command[:4] == [
        str(Path("D:/4/claude2openai/.venv/Scripts/pythonw.exe")),
        "-m",
        "uvicorn",
        "claude2openai_gateway.fixup_server:app",
    ]
    assert spec.command[-4:] == [
        "--host",
        "127.0.0.1",
        "--port",
        "8328",
    ]
    assert spec.env["BACKEND_API_BASE"] == "http://127.0.0.1:8327/v1"
    assert spec.env["BACKEND_API_KEY"] == "real-key"
    assert spec.env["PYTHONPATH"] == str(Path("D:/4/claude2openai/src"))


def test_build_gateway_launch_spec_points_litellm_at_fixup_proxy():
    spec = build_gateway_launch_spec(
        repo_root=Path("D:/4/claude2openai"),
        openai_base_url="http://127.0.0.1:8328/v1",
        openai_api_key="real-key",
        gateway_model="gpt-5.5",
        openai_model="openai/gpt-5.5",
        gateway_key="local-gateway-key",
        port=4000,
    )

    assert spec.command[:3] == [
        str(Path("D:/4/claude2openai/.venv/Scripts/pythonw.exe")),
        "-m",
        "claude2openai_gateway.litellm_proxy",
    ]
    assert spec.command[-4:] == [
        "--host",
        "127.0.0.1",
        "--port",
        "4000",
    ]
    assert spec.env["OPENAI_API_BASE"] == "http://127.0.0.1:8328/v1"
    assert spec.env["OPENAI_API_KEY"] == "real-key"
    assert spec.env["OPENAI_MODEL"] == "openai/gpt-5.5"
    assert spec.env["GATEWAY_MODEL"] == "gpt-5.5"
    assert spec.env["LITELLM_MASTER_KEY"] == "local-gateway-key"


def test_resolve_backend_api_key_prefers_cli_then_backend_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BACKEND_API_KEY", "backend-env-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-env-key")

    assert resolve_backend_api_key("cli-key") == "cli-key"
    assert resolve_backend_api_key(None) == "backend-env-key"


def test_resolve_backend_api_key_falls_back_to_openai_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("BACKEND_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-env-key")

    assert resolve_backend_api_key(None) == "openai-env-key"


def test_load_repo_config_reads_gateway_config_toml(tmp_path: Path):
    (tmp_path / "gateway_config.toml").write_text(
        """
[backend]
api_key = "proxy-key"
base_url = "http://127.0.0.1:8327/v1"

[gateway]
key = "local-gateway-key"
model = "gpt-5.5"
openai_model = "openai/gpt-5.5"

[ports]
fixup = 9328
gateway = 5000
""".strip(),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert config["backend"]["api_key"] == "proxy-key"
    assert config["backend"]["base_url"] == "http://127.0.0.1:8327/v1"
    assert config["gateway"]["key"] == "local-gateway-key"
    assert config["gateway"]["model"] == "gpt-5.5"
    assert config["gateway"]["openai_model"] == "openai/gpt-5.5"
    assert config["ports"]["fixup"] == 9328
    assert config["ports"]["gateway"] == 5000


def test_resolve_backend_api_key_falls_back_to_repo_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("BACKEND_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / "gateway_config.toml").write_text(
        """
[backend]
api_key = "proxy-key"
""".strip(),
        encoding="utf-8",
    )

    assert resolve_backend_api_key(None, load_repo_config(tmp_path)) == "proxy-key"


def test_main_start_uses_repo_config_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    (tmp_path / "gateway_config.toml").write_text(
        """
[backend]
api_key = "proxy-key"
base_url = "http://127.0.0.1:9001/v1"

[gateway]
key = "committed-gateway-key"
model = "gpt-5.5"
openai_model = "openai/gpt-5.5"

[ports]
fixup = 9328
gateway = 5000
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.delenv("BACKEND_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    captured_specs: list[LaunchSpec] = []

    def fake_ensure_service_started(spec: LaunchSpec, timeout_seconds: float):
        captured_specs.append(spec)
        return bootstrap.StartResult(
            action="started",
            status=bootstrap.ServiceStatus(
                name=spec.name,
                port=spec.port,
                pid=123,
                pid_file_exists=True,
                process_running=True,
                port_open=True,
                state="running",
                log_path=spec.log_path,
                pid_path=spec.pid_path,
            ),
        )

    monkeypatch.setattr(bootstrap, "ensure_service_started", fake_ensure_service_started)
    monkeypatch.setattr(bootstrap, "_print_ready_summary", lambda *args, **kwargs: None)

    exit_code = bootstrap.main(["start", "--repo-root", str(tmp_path), "--skip-smoke"])

    assert exit_code == 0
    assert len(captured_specs) == 2
    fixup_spec, gateway_spec = captured_specs
    assert fixup_spec.port == 9328
    assert fixup_spec.env["BACKEND_API_BASE"] == "http://127.0.0.1:9001/v1"
    assert fixup_spec.env["BACKEND_API_KEY"] == "proxy-key"
    assert gateway_spec.port == 5000
    assert gateway_spec.env["OPENAI_API_BASE"] == "http://127.0.0.1:9328/v1"
    assert gateway_spec.env["OPENAI_API_KEY"] == "proxy-key"
    assert gateway_spec.env["LITELLM_MASTER_KEY"] == "committed-gateway-key"


def test_main_start_converts_timeout_to_clean_cli_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    (tmp_path / "gateway_config.toml").write_text(
        """
[backend]
api_key = "proxy-key"
""".strip(),
        encoding="utf-8",
    )

    def raise_timeout(spec: LaunchSpec, timeout_seconds: float):
        raise TimeoutError("Timed out waiting for startup")

    monkeypatch.setattr(bootstrap, "ensure_service_started", raise_timeout)

    with pytest.raises(SystemExit, match="Timed out waiting for startup"):
        bootstrap.main(["start", "--repo-root", str(tmp_path), "--skip-smoke"])


def test_main_stop_converts_timeout_to_clean_cli_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    def raise_timeout(spec: LaunchSpec, timeout_seconds: float):
        raise TimeoutError("Timed out waiting for shutdown")

    monkeypatch.setattr(bootstrap, "stop_service", raise_timeout)

    with pytest.raises(SystemExit, match="Timed out waiting for shutdown"):
        bootstrap.main(["stop", "--repo-root", str(tmp_path)])


def test_main_start_default_output_is_concise(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    (tmp_path / "gateway_config.toml").write_text(
        """
[backend]
api_key = "proxy-key"
""".strip(),
        encoding="utf-8",
    )

    def fake_ensure_service_started(spec: LaunchSpec, timeout_seconds: float):
        return bootstrap.StartResult(
            action="started",
            status=bootstrap.ServiceStatus(
                name=spec.name,
                port=spec.port,
                pid=123 if spec.name == "fixup" else 456,
                pid_file_exists=True,
                process_running=True,
                port_open=True,
                state="running",
                log_path=spec.log_path,
                pid_path=spec.pid_path,
            ),
        )

    monkeypatch.setattr(bootstrap, "ensure_service_started", fake_ensure_service_started)
    monkeypatch.setattr(
        bootstrap,
        "run_backend_smoke",
        lambda **kwargs: {"target": "backend", "returned_model": "gpt-5.4"},
    )
    monkeypatch.setattr(
        bootstrap,
        "run_gateway_smoke",
        lambda **kwargs: {"target": "gateway", "returned_model": "gpt-5.5"},
    )

    exit_code = bootstrap.main(["start", "--repo-root", str(tmp_path)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Ready:" in output
    assert "== Fixup smoke ==" not in output
    assert "== Gateway smoke ==" not in output
    assert "== CC Switch env ==" not in output
    assert "ANTHROPIC_AUTH_TOKEN" not in output
    assert "state=" not in output
    assert "log=" not in output


def test_main_start_verbose_output_includes_smoke_and_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    (tmp_path / "gateway_config.toml").write_text(
        """
[backend]
api_key = "proxy-key"
""".strip(),
        encoding="utf-8",
    )

    def fake_ensure_service_started(spec: LaunchSpec, timeout_seconds: float):
        return bootstrap.StartResult(
            action="started",
            status=bootstrap.ServiceStatus(
                name=spec.name,
                port=spec.port,
                pid=123 if spec.name == "fixup" else 456,
                pid_file_exists=True,
                process_running=True,
                port_open=True,
                state="running",
                log_path=spec.log_path,
                pid_path=spec.pid_path,
            ),
        )

    monkeypatch.setattr(bootstrap, "ensure_service_started", fake_ensure_service_started)
    monkeypatch.setattr(
        bootstrap,
        "run_backend_smoke",
        lambda **kwargs: {"target": "backend", "returned_model": "gpt-5.4"},
    )
    monkeypatch.setattr(
        bootstrap,
        "run_gateway_smoke",
        lambda **kwargs: {"target": "gateway", "returned_model": "gpt-5.5"},
    )

    exit_code = bootstrap.main(["start", "--repo-root", str(tmp_path), "--verbose"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "== Fixup smoke ==" in output
    assert "== Gateway smoke ==" in output
    assert "== CC Switch env ==" in output
    assert "ANTHROPIC_AUTH_TOKEN" in output


def _make_launch_spec(tmp_path: Path, name: str = "gateway", port: int = 4000) -> LaunchSpec:
    return LaunchSpec(
        name=name,
        port=port,
        command=["python", "-m", "dummy"],
        env={},
        cwd=tmp_path,
        log_path=tmp_path / f"{name}.log",
        pid_path=tmp_path / f"{name}.pid",
    )


def test_normalize_cli_argv_defaults_to_start_command():
    assert normalize_cli_argv([]) == ["start"]
    assert normalize_cli_argv(["--skip-smoke"]) == ["start", "--skip-smoke"]
    assert normalize_cli_argv(["status"]) == ["status"]


def test_inspect_service_marks_port_without_managed_pid_as_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _make_launch_spec(tmp_path)
    monkeypatch.setattr(bootstrap, "is_port_open", lambda host, port, timeout=0.2: True)

    status = inspect_service(spec)

    assert status.state == "conflict"
    assert status.pid is None
    assert status.process_running is False


def test_inspect_service_marks_live_pid_without_port_as_starting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _make_launch_spec(tmp_path)
    spec.pid_path.write_text("123", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "process_exists", lambda pid: pid == 123)
    monkeypatch.setattr(bootstrap, "is_port_open", lambda host, port, timeout=0.2: False)

    status = inspect_service(spec)

    assert status.state == "starting"
    assert status.pid == 123
    assert status.process_running is True


def test_ensure_service_started_reuses_running_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _make_launch_spec(tmp_path)
    running_status = bootstrap.ServiceStatus(
        name=spec.name,
        port=spec.port,
        pid=123,
        pid_file_exists=True,
        process_running=True,
        port_open=True,
        state="running",
        log_path=spec.log_path,
        pid_path=spec.pid_path,
    )

    monkeypatch.setattr(bootstrap, "inspect_service", lambda service_spec: running_status)
    monkeypatch.setattr(
        bootstrap,
        "start_detached_process",
        lambda service_spec: (_ for _ in ()).throw(AssertionError("should not start a duplicate process")),
    )

    result = ensure_service_started(spec, timeout_seconds=1.0)

    assert result.action == "reused"
    assert result.status is running_status


def test_ensure_service_started_errors_on_unknown_port_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    spec = _make_launch_spec(tmp_path)
    conflict_status = bootstrap.ServiceStatus(
        name=spec.name,
        port=spec.port,
        pid=None,
        pid_file_exists=False,
        process_running=False,
        port_open=True,
        state="conflict",
        log_path=spec.log_path,
        pid_path=spec.pid_path,
    )

    monkeypatch.setattr(bootstrap, "inspect_service", lambda service_spec: conflict_status)

    with pytest.raises(RuntimeError, match="unknown process"):
        ensure_service_started(spec, timeout_seconds=1.0)


def test_root_bootstrap_script_forwards_status_subcommand():
    repo_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [sys.executable, str(repo_root / "bootstrap_claude_gateway.py"), "status"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "fixup: state=" in result.stdout
    assert "gateway: state=" in result.stdout


def test_process_exists_uses_tasklist_output_on_windows(monkeypatch: pytest.MonkeyPatch):
    class Result:
        def __init__(self, stdout: str):
            self.stdout = stdout

    monkeypatch.setattr(bootstrap.os, "name", "nt")
    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda *args, **kwargs: Result('"python.exe","123","Console","1","12,000 K"\r\n'),
    )

    assert bootstrap.process_exists(123) is True

    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda *args, **kwargs: Result("INFO: No tasks are running which match the specified criteria.\r\n"),
    )

    assert bootstrap.process_exists(123) is False
