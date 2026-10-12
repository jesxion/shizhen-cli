"""令牌与服务地址的读取、保存。令牌永远不打印。"""
import json
import os

DEFAULT_API = "https://jesxion.com"


def config_dir(env):
    override = env.get("SHIZHEN_CONFIG_DIR")
    if override:
        return override
    if os.name == "nt":
        base = env.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(base, "shizhen")
    return os.path.join(os.path.expanduser("~"), ".config", "shizhen")


def config_path(env):
    return os.path.join(config_dir(env), "config.json")


def api_base(env):
    return (env.get("SHIZHEN_API") or DEFAULT_API).rstrip("/")


def load_token(env):
    """环境变量优先，其次配置文件。找不到返回 None。"""
    token = (env.get("SHIZHEN_TOKEN") or "").strip()
    if token:
        return token
    try:
        with open(config_path(env), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    token = data.get("token") if isinstance(data, dict) else None
    return token.strip() if isinstance(token, str) and token.strip() else None


def save_token(env, token):
    path = config_path(env)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"token": token}, handle)
    if os.name != "nt":
        os.chmod(path, 0o600)
    return path


def delete_token(env):
    try:
        os.remove(config_path(env))
        return True
    except FileNotFoundError:
        return False
