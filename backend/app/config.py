from dataclasses import dataclass, field
import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv(BACKEND_DIR / ".env")


TRUE_VALUES = {"1", "true", "yes", "on"}


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_csv(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return default
    items = [item.strip() for item in value.split(",")]
    return [item for item in items if item]


def env_path(name: str, default: str) -> str:
    value = os.getenv(name, default)
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str(BACKEND_DIR / path)


@dataclass(frozen=True)
class Settings:
    openf1_base_url: str = os.getenv(
        "OPENF1_BASE_URL", "https://api.openf1.org/v1"
    )
    jolpica_base_url: str = os.getenv(
        "JOLPICA_BASE_URL", "https://api.jolpi.ca/ergast/f1"
    )
    cors_allowed_origins: list[str] = field(
        default_factory=lambda: env_csv(
            "CORS_ALLOWED_ORIGINS",
            ["http://localhost:5173"],
        )
    )
    cache_ttl_seconds: int = env_int("CACHE_TTL_SECONDS", 60)
    requests_per_second: int = env_int("OPENF1_REQUESTS_PER_SECOND", 3)
    requests_per_minute: int = env_int("OPENF1_REQUESTS_PER_MINUTE", 30)
    enable_openf1_history: bool = env_bool("ENABLE_OPENF1_HISTORY", False)
    fastf1_cache_dir: str = env_path("FASTF1_CACHE_DIR", ".cache/fastf1")
    open_meteo_base_url: str = os.getenv(
        "OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1"
    )
    open_meteo_archive_url: str = os.getenv(
        "OPEN_METEO_ARCHIVE_URL", "https://archive-api.open-meteo.com/v1"
    )
    f1_signalr_connection_url: str = os.getenv(
        "F1_SIGNALR_CONNECTION_URL",
        "wss://livetiming.formula1.com/signalrcore",
    )
    f1_signalr_negotiate_url: str = os.getenv(
        "F1_SIGNALR_NEGOTIATE_URL",
        "https://livetiming.formula1.com/signalrcore/negotiate",
    )
    f1_signalr_auth_token: str | None = os.getenv("F1_SIGNALR_AUTH_TOKEN")
    f1_signalr_login_session: str | None = os.getenv("F1_SIGNALR_LOGIN_SESSION")
    f1_signalr_timeout_seconds: int = env_int("F1_SIGNALR_TIMEOUT_SECONDS", 90)
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_transcription_model: str = os.getenv(
        "OPENAI_TRANSCRIPTION_MODEL",
        "gpt-4o-transcribe",
    )
    openai_translation_model: str = os.getenv(
        "OPENAI_TRANSLATION_MODEL",
        "gpt-5.2",
    )
    team_radio_transcription_provider: str = os.getenv(
        "TEAM_RADIO_TRANSCRIPTION_PROVIDER",
        "local",
    ).lower()
    team_radio_translation_provider: str = os.getenv(
        "TEAM_RADIO_TRANSLATION_PROVIDER",
        "googletrans",
    ).lower()
    team_radio_local_whisper_model: str = os.getenv(
        "TEAM_RADIO_LOCAL_WHISPER_MODEL",
        "base",
    )
    team_radio_local_whisper_device: str = os.getenv(
        "TEAM_RADIO_LOCAL_WHISPER_DEVICE",
        "auto",
    )
    team_radio_local_whisper_compute_type: str = os.getenv(
        "TEAM_RADIO_LOCAL_WHISPER_COMPUTE_TYPE",
        "float32",
    )
    team_radio_auto_transcription_enabled: bool = env_bool(
        "TEAM_RADIO_AUTO_TRANSCRIPTION_ENABLED",
        True,
    )
    team_radio_auto_transcription_concurrency: int = env_int(
        "TEAM_RADIO_AUTO_TRANSCRIPTION_CONCURRENCY",
        1,
    )
    team_radio_auto_translate_enabled: bool = env_bool(
        "TEAM_RADIO_AUTO_TRANSLATE_ENABLED",
        False,
    )
    team_radio_transcription_cache_enabled: bool = env_bool(
        "TEAM_RADIO_TRANSCRIPTION_CACHE_ENABLED",
        True,
    )
    f1_signalr_archive_enabled: bool = env_bool("F1_SIGNALR_ARCHIVE_ENABLED", True)
    f1_signalr_archive_dir: str = env_path(
        "F1_SIGNALR_ARCHIVE_DIR",
        ".cache/f1signal",
    )
    f1_signalr_snapshot_archive_interval_seconds: int = env_int(
        "F1_SIGNALR_SNAPSHOT_ARCHIVE_INTERVAL_SECONDS",
        5,
    )
    prediction_upgrades_file: str = env_path(
        "PREDICTION_UPGRADES_FILE",
        ".cache/predictions/team_upgrades.json",
    )


settings = Settings()
