from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from pathlib import Path
import sys
import re
import os

try:
    import tomllib as toml_loader
except Exception:
    try:
        import tomli as toml_loader
    except Exception:
        toml_loader = None


def _resolve_env_string(value: str) -> str:
    if isinstance(value, str) and re.fullmatch(r"ENV_[A-Z0-9_]+", value):
        var_name = value[4:]
        env_val = os.getenv(var_name)
        if env_val is None:
            print(
                f"Warning: Environment variable '{var_name}' not set for placeholder '{value}'"
            )
            return value
        return env_val
    return value


def _resolve_env_placeholders(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _resolve_env_placeholders(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_placeholders(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_resolve_env_placeholders(v) for v in obj)
    if isinstance(obj, str):
        return _resolve_env_string(obj)
    return obj


def load_config(config_path: Optional[str]) -> Dict[str, Any]:
    if not config_path:
        return {}
    if toml_loader is None:
        print(
            "TOML support not available. Install 'tomli' for Python < 3.11 or use Python 3.11+."
        )
        sys.exit(1)
    cfg_path = Path(config_path)
    if not cfg_path.exists():
        print(f"Config file not found: {cfg_path}")
        sys.exit(1)
    try:
        with cfg_path.open("rb") as fp:
            data: Dict[str, Any] = toml_loader.load(fp)
    except Exception as err:
        print(f"Failed to read config TOML: {err}")
        sys.exit(1)

    try:
        default_env = cfg_path.parent / ".env"
        if default_env.exists():
            load_dotenv(dotenv_path=str(default_env), override=False)
    except Exception:
        pass

    dot_env = data.get("dot_env")
    dot_envs = data.get("dot_envs") or []
    env_paths: List[Path] = []
    if isinstance(dot_env, str) and dot_env:
        env_paths.append((cfg_path.parent / dot_env))
    if isinstance(dot_envs, list):
        for p in dot_envs:
            if isinstance(p, str) and p:
                env_paths.append((cfg_path.parent / p))
    for p in env_paths:
        try:
            load_dotenv(dotenv_path=str(p), override=False)
        except Exception:
            pass

    data = _resolve_env_placeholders(data)
    return data
