import os


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


DATA_DIR = env("DATA_DIR", "/var/lib/dashboard")
REDIS_URL = env("REDIS_URL")
EXECUTOR_URL = env("EXECUTOR_URL", "http://server-executor:8090").rstrip("/")
EXECUTOR_TOKEN = env("EXECUTOR_TOKEN")
AUTHENTIK_INTERNAL = env("AUTHENTIK_INTERNAL_URL", "http://server-authentik:9000").rstrip("/")
AUTHENTIK_BROWSER = env("AUTHENTIK_BROWSER_URL", "https://auth.example.com").rstrip("/")
AUTHENTIK_TOKEN = env("AUTHENTIK_BOOTSTRAP_TOKEN")
OIDC_CLIENT_ID = env("DASHBOARD_OIDC_CLIENT_ID", "dashboard")
OIDC_SECRET = env("DASHBOARD_OIDC_SECRET")
DASHBOARD_HOST = env("DASHBOARD_HOST", "dashboard.example.com")
PUBLIC_URL = env("DASHBOARD_PUBLIC_URL", f"https://{DASHBOARD_HOST}").rstrip("/")
PROMETHEUS_URL = env("PROMETHEUS_URL", "http://server-prometheus:9090").rstrip("/")
VLLM_URL = env("VLLM_URL", "http://server-vllm:8000").rstrip("/")
VLLM_MODEL = env("VLLM_MODEL")
VLLM_MANAGER_URL = env("VLLM_MANAGER_URL", "http://server-vllm-manager:8000").rstrip("/")
VLLM_MANAGER_MODEL = env("VLLM_MANAGER_MODEL")
LLMLINGUA_URL = env("LLMLINGUA_URL", "http://server-llmlingua:8000").rstrip("/")
COOLIFY_API_URL = env("COOLIFY_API_URL", "http://server-coolify:8080").rstrip("/")
COOLIFY_API_TOKEN = env("COOLIFY_API_TOKEN")
WEBSITES_FILE = env("WEBSITES_FILE", "/config/websites.json")
SESSION_HOURS = int(env("SESSION_HOURS", "12") or "12")
CHAT_RETENTION_DAYS = int(env("CHAT_RETENTION_DAYS", "90") or "90")
DEV_AUTH = env("DASHBOARD_DEV_AUTH") == "1"

HOSTS = {
    "dashboard": env("DASHBOARD_HOST"),
    "auth": env("AUTH_HOST"),
    "media": env("MEDIA_HOST"),
    "git": env("GIT_HOST"),
    "files": env("FILES_HOST"),
    "office": env("OFFICE_HOST"),
    "apps": env("APPS_HOST"),
    "notify": env("NOTIFY_HOST"),
    "grafana": env("GRAFANA_HOST"),
}
