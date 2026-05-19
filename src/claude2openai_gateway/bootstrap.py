from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .smoke import run_backend_smoke, run_gateway_smoke


@dataclass(frozen=True)
class LaunchSpec:
    name: str
    port: int
    command: list[str]
    env: dict[str, str]
    cwd: Path
    log_path: Path
    pid_path: Path


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    port: int
    pid: int | None
    pid_file_exists: bool
    process_running: bool
    port_open: bool
    state: str
    log_path: Path
    pid_path: Path


@dataclass(frozen=True)
class StartResult:
    action: str
    status: ServiceStatus


DEFAULT_BACKEND_BASE_URL = "http://127.0.0.1:8327/v1"
DEFAULT_GATEWAY_MODEL = "gpt-5.5"
DEFAULT_OPENAI_MODEL = "openai/gpt-5.5"
DEFAULT_GATEWAY_KEY = "local-gateway-key"
DEFAULT_FIXUP_PORT = 8328
DEFAULT_GATEWAY_PORT = 4000
DEFAULT_GATEWAY_CONFIG = "gateway_config.toml"
MANAGED_SERVICE_ERRORS = (RuntimeError, TimeoutError)


def build_cc_switch_env(
    gateway_url: str,
    gateway_key: str,
    gateway_model: str,
) -> dict[str, str]:
    return {
        "ANTHROPIC_AUTH_TOKEN": gateway_key,
        "ANTHROPIC_BASE_URL": gateway_url,
        "ANTHROPIC_CUSTOM_MODEL_OPTION": gateway_model,
        "ANTHROPIC_CUSTOM_MODEL_OPTION_NAME": gateway_model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": gateway_model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": gateway_model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME": gateway_model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": gateway_model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME": gateway_model,
    }


def build_fixup_launch_spec(
    repo_root: Path,
    backend_base_url: str,
    backend_api_key: str,
    port: int,
) -> LaunchSpec:
    runtime_dir = ensure_runtime_dir(repo_root)
    pythonw = str(repo_root / ".venv" / "Scripts" / "pythonw.exe")
    env = os.environ.copy()
    env["BACKEND_API_BASE"] = backend_base_url
    env["BACKEND_API_KEY"] = backend_api_key
    env["PYTHONPATH"] = str(repo_root / "src")
    return LaunchSpec(
        name="fixup",
        port=port,
        command=[
            pythonw,
            "-m",
            "uvicorn",
            "claude2openai_gateway.fixup_server:app",
            "--app-dir",
            str(repo_root / "src"),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        cwd=repo_root,
        log_path=runtime_dir / "fixup.log",
        pid_path=runtime_dir / "fixup.pid",
    )


def build_gateway_launch_spec(
    repo_root: Path,
    openai_base_url: str,
    openai_api_key: str,
    gateway_model: str,
    openai_model: str,
    gateway_key: str,
    port: int,
) -> LaunchSpec:
    runtime_dir = ensure_runtime_dir(repo_root)
    pythonw = str(repo_root / ".venv" / "Scripts" / "pythonw.exe")
    env = os.environ.copy()
    env.pop("DEBUG", None)
    env["OPENAI_API_BASE"] = openai_base_url
    env["OPENAI_API_KEY"] = openai_api_key
    env["OPENAI_MODEL"] = openai_model
    env["GATEWAY_MODEL"] = gateway_model
    env["LITELLM_MASTER_KEY"] = gateway_key
    env["PYTHONPATH"] = str(repo_root / "src")
    return LaunchSpec(
        name="gateway",
        port=port,
        command=[
            pythonw,
            "-m",
            "claude2openai_gateway.litellm_proxy",
            "--config",
            str(repo_root / "litellm_config.yaml"),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        cwd=repo_root,
        log_path=runtime_dir / "gateway.log",
        pid_path=runtime_dir / "gateway.pid",
    )


def ensure_runtime_dir(repo_root: Path) -> Path:
    runtime_dir = repo_root / ".runtime"
    runtime_dir.mkdir(exist_ok=True)
    return runtime_dir


def is_port_open(host: str, port: int, timeout: float = 0.2) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def wait_for_port(host: str, port: int, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if is_port_open(host, port):
            return
        time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for {host}:{port}")


def wait_for_port_closed(host: str, port: int, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not is_port_open(host, port):
            return
        time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for {host}:{port} to close")


def start_detached_process(spec: LaunchSpec) -> int:
    spec.log_path.parent.mkdir(exist_ok=True)
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NO_WINDOW
        )

    with spec.log_path.open("ab") as log_handle:
        process = subprocess.Popen(
            spec.command,
            cwd=spec.cwd,
            env=spec.env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )

    spec.pid_path.write_text(str(process.pid), encoding="utf-8")
    return process.pid


def normalize_cli_argv(argv: list[str] | None) -> list[str]:
    normalized = list(argv or [])
    if not normalized or normalized[0].startswith("-"):
        return ["start", *normalized]
    return normalized


def load_repo_config(repo_root: Path) -> dict[str, Any]:
    config_path = repo_root / DEFAULT_GATEWAY_CONFIG
    if not config_path.exists():
        return {}

    try:
        with config_path.open("rb") as config_file:
            data = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"Invalid {config_path.name}: {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"Invalid {config_path.name}: top-level TOML value must be a table.")
    return data


def _config_section(repo_config: dict[str, Any], name: str) -> dict[str, Any]:
    section = repo_config.get(name, {})
    if not isinstance(section, dict):
        raise SystemExit(f"Invalid {DEFAULT_GATEWAY_CONFIG}: [{name}] must be a table.")
    return section


def _config_str(repo_config: dict[str, Any], section: str, key: str) -> str | None:
    value = _config_section(repo_config, section).get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise SystemExit(f"Invalid {DEFAULT_GATEWAY_CONFIG}: [{section}].{key} must be a string.")
    return value


def _config_int(repo_config: dict[str, Any], section: str, key: str) -> int | None:
    value = _config_section(repo_config, section).get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise SystemExit(f"Invalid {DEFAULT_GATEWAY_CONFIG}: [{section}].{key} must be an integer.")
    return value


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--fixup-port", type=int)
    parser.add_argument("--gateway-port", type=int)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)


def _add_start_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--openai-api-key")
    parser.add_argument("--backend-base-url")
    parser.add_argument("--gateway-model")
    parser.add_argument("--openai-model")
    parser.add_argument("--gateway-key")
    smoke_group = parser.add_mutually_exclusive_group()
    smoke_group.add_argument("--smoke", dest="run_smoke", action="store_true")
    smoke_group.add_argument("--skip-smoke", dest="run_smoke", action="store_false", help=argparse.SUPPRESS)
    parser.set_defaults(run_smoke=False)
    parser.add_argument("--verbose", action="store_true")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start local Claude gateway services")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Start or reuse the managed services")
    _add_common_args(start_parser)
    _add_start_args(start_parser)

    restart_parser = subparsers.add_parser("restart", help="Restart the managed services")
    _add_common_args(restart_parser)
    _add_start_args(restart_parser)

    stop_parser = subparsers.add_parser("stop", help="Stop the managed services started by this bootstrap flow")
    _add_common_args(stop_parser)

    status_parser = subparsers.add_parser("status", help="Show managed service status")
    _add_common_args(status_parser)

    return parser


def resolve_backend_api_key(cli_value: str | None, repo_config: dict[str, Any] | None = None) -> str:
    api_key = (
        cli_value
        or os.getenv("BACKEND_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or _config_str(repo_config or {}, "backend", "api_key")
    )
    if not api_key:
        raise SystemExit(
            "Set BACKEND_API_KEY or OPENAI_API_KEY, pass --openai-api-key, "
            f"or configure [backend].api_key in {DEFAULT_GATEWAY_CONFIG}."
        )
    return api_key


def read_pid_file(pid_path: Path) -> int | None:
    if not pid_path.exists():
        return None
    try:
        raw_value = pid_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw_value:
        return None
    try:
        return int(raw_value)
    except ValueError:
        return None


def process_exists(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        output = result.stdout.strip()
        if not output or output.startswith("INFO:"):
            return False
        return output.startswith('"')
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def inspect_service(spec: LaunchSpec) -> ServiceStatus:
    pid_file_exists = spec.pid_path.exists()
    pid = read_pid_file(spec.pid_path)
    process_running = process_exists(pid)
    port_open = is_port_open("127.0.0.1", spec.port)

    if pid is not None and process_running:
        state = "running" if port_open else "starting"
    elif port_open:
        state = "conflict"
    elif pid_file_exists:
        state = "stale_pid"
    else:
        state = "stopped"

    return ServiceStatus(
        name=spec.name,
        port=spec.port,
        pid=pid,
        pid_file_exists=pid_file_exists,
        process_running=process_running,
        port_open=port_open,
        state=state,
        log_path=spec.log_path,
        pid_path=spec.pid_path,
    )


def _cleanup_pid_file(spec: LaunchSpec) -> None:
    try:
        spec.pid_path.unlink(missing_ok=True)
    except OSError:
        pass


def ensure_service_started(spec: LaunchSpec, timeout_seconds: float) -> StartResult:
    status = inspect_service(spec)

    if status.state == "running":
        return StartResult(action="reused", status=status)

    if status.state == "starting":
        wait_for_port("127.0.0.1", spec.port, timeout_seconds)
        return StartResult(action="waited", status=inspect_service(spec))

    if status.state == "conflict":
        raise RuntimeError(
            f"{spec.name} port {spec.port} is already in use by an unknown process. "
            f"Stop that process or run `status` before starting this gateway."
        )

    if status.state == "stale_pid":
        _cleanup_pid_file(spec)

    start_detached_process(spec)
    wait_for_port("127.0.0.1", spec.port, timeout_seconds)
    return StartResult(action="started", status=inspect_service(spec))


def terminate_process(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    os.kill(pid, signal.SIGTERM)


def wait_for_process_exit(pid: int, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not process_exists(pid):
            return
        time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for pid {pid} to exit")


def stop_service(spec: LaunchSpec, timeout_seconds: float) -> ServiceStatus:
    status = inspect_service(spec)

    if status.state == "conflict":
        raise RuntimeError(
            f"{spec.name} port {spec.port} is in use by an unknown process. "
            "Refusing to stop a process this bootstrap flow did not start."
        )

    if status.pid is not None and status.process_running:
        terminate_process(status.pid)
        wait_for_process_exit(status.pid, timeout_seconds)
        if status.port_open:
            wait_for_port_closed("127.0.0.1", spec.port, timeout_seconds)
        _cleanup_pid_file(spec)
        return inspect_service(spec)

    if status.pid_file_exists:
        _cleanup_pid_file(spec)

    return inspect_service(spec)


def _format_service_status(status: ServiceStatus) -> str:
    pid_text = str(status.pid) if status.pid is not None else "none"
    return (
        f"{status.name}: state={status.state}, port={status.port}, pid={pid_text}, "
        f"log={status.log_path}"
    )


def _format_service_summary(result: StartResult) -> str:
    pid_text = str(result.status.pid) if result.status.pid is not None else "none"
    return (
        f"{result.status.name}: {result.action}, {result.status.state} "
        f"on 127.0.0.1:{result.status.port} (pid {pid_text})"
    )


def _print_service_statuses(specs: list[LaunchSpec]) -> None:
    for spec in specs:
        print(_format_service_status(inspect_service(spec)))


def _print_ready_summary(
    gateway_url: str,
    gateway_key: str,
    gateway_model: str,
    smoke_results: dict[str, Any] | None,
    fixup_result: StartResult,
    gateway_result: StartResult,
    verbose: bool,
) -> None:
    if verbose and smoke_results:
        print("== Fixup smoke ==")
        print(json.dumps(smoke_results["fixup"], ensure_ascii=False, indent=2))
        print("")
        print("== Gateway smoke ==")
        print(json.dumps(smoke_results["gateway"], ensure_ascii=False, indent=2))
        print("")

    print(f"Ready: Claude should point at {gateway_url}")
    print(f"Model: {gateway_model}")
    print(f"Gateway key: {gateway_key}")
    print(_format_service_summary(fixup_result))
    print(_format_service_summary(gateway_result))

    if verbose:
        print("")
        print("== CC Switch env ==")
        print(
            json.dumps(
                build_cc_switch_env(
                    gateway_url=gateway_url,
                    gateway_key=gateway_key,
                    gateway_model=gateway_model,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    normalized_argv = normalize_cli_argv(argv)
    parser = _build_parser()
    args = parser.parse_args(normalized_argv)

    repo_root = Path(args.repo_root).resolve()
    repo_config = load_repo_config(repo_root)
    backend_base_url = (
        getattr(args, "backend_base_url", None)
        or _config_str(repo_config, "backend", "base_url")
        or DEFAULT_BACKEND_BASE_URL
    )
    gateway_model = (
        getattr(args, "gateway_model", None)
        or _config_str(repo_config, "gateway", "model")
        or DEFAULT_GATEWAY_MODEL
    )
    openai_model = (
        getattr(args, "openai_model", None)
        or _config_str(repo_config, "gateway", "openai_model")
        or DEFAULT_OPENAI_MODEL
    )
    gateway_key = (
        getattr(args, "gateway_key", None)
        or _config_str(repo_config, "gateway", "key")
        or DEFAULT_GATEWAY_KEY
    )
    run_smoke = getattr(args, "run_smoke", False)
    verbose = getattr(args, "verbose", False)
    openai_api_key_arg = getattr(args, "openai_api_key", None)
    fixup_port = args.fixup_port or _config_int(repo_config, "ports", "fixup") or DEFAULT_FIXUP_PORT
    gateway_port = args.gateway_port or _config_int(repo_config, "ports", "gateway") or DEFAULT_GATEWAY_PORT
    backend_api_key = ""
    if args.command in {"start", "restart"}:
        backend_api_key = resolve_backend_api_key(openai_api_key_arg, repo_config)

    fixup_base_url = f"http://127.0.0.1:{fixup_port}/v1"
    gateway_url = f"http://127.0.0.1:{gateway_port}"

    fixup_spec = build_fixup_launch_spec(
        repo_root=repo_root,
        backend_base_url=backend_base_url,
        backend_api_key=backend_api_key,
        port=fixup_port,
    )
    gateway_spec = build_gateway_launch_spec(
        repo_root=repo_root,
        openai_base_url=fixup_base_url,
        openai_api_key=backend_api_key,
        gateway_model=gateway_model,
        openai_model=openai_model,
        gateway_key=gateway_key,
        port=gateway_port,
    )

    service_specs = [fixup_spec, gateway_spec]

    if args.command == "status":
        _print_service_statuses(service_specs)
        return 0

    if args.command == "stop":
        try:
            for spec in reversed(service_specs):
                stop_service(spec, args.timeout_seconds)
        except MANAGED_SERVICE_ERRORS as exc:
            raise SystemExit(str(exc)) from exc
        _print_service_statuses(service_specs)
        return 0

    if args.command == "restart":
        try:
            for spec in reversed(service_specs):
                stop_service(spec, args.timeout_seconds)
        except MANAGED_SERVICE_ERRORS as exc:
            raise SystemExit(str(exc)) from exc

    try:
        fixup_result = ensure_service_started(fixup_spec, args.timeout_seconds)
        gateway_result = ensure_service_started(gateway_spec, args.timeout_seconds)
    except MANAGED_SERVICE_ERRORS as exc:
        raise SystemExit(str(exc)) from exc

    smoke_results: dict[str, Any] | None = None
    if run_smoke:
        try:
            smoke_results = {
                "fixup": run_backend_smoke(
                    base_url=fixup_base_url,
                    api_key=backend_api_key,
                    model=gateway_model,
                    prompt="你好",
                ),
                "gateway": run_gateway_smoke(
                    base_url=gateway_url,
                    api_key=gateway_key,
                    model=gateway_model,
                    prompt="你好",
                ),
            }
        except httpx.HTTPError as exc:
            raise SystemExit(
                "Startup smoke check failed. Verify BACKEND_API_KEY or --openai-api-key "
                "points at the real 8327 backend key.\n"
                f"Fixup log: {fixup_spec.log_path}\n"
                f"Gateway log: {gateway_spec.log_path}\n"
                f"Original error: {exc}"
            ) from exc

    _print_ready_summary(
        gateway_url=gateway_url,
        gateway_key=gateway_key,
        gateway_model=gateway_model,
        smoke_results=smoke_results,
        fixup_result=fixup_result,
        gateway_result=gateway_result,
        verbose=verbose,
    )
    print("")
    print(f"Fixup log: {fixup_spec.log_path}")
    print(f"Gateway log: {gateway_spec.log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
