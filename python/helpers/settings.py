import base64
import hashlib
import json
import os
import re
import subprocess
from typing import Any, Literal, TypedDict, cast, TypeVar

import models
from python.helpers import runtime, whisper, defer, git
from . import files, dotenv
from python.helpers.print_style import PrintStyle
from python.helpers.providers import get_providers, FieldOption as ProvidersFO
from python.helpers.secrets import get_default_secrets_manager
from python.helpers import dirty_json
from python.helpers.notification import NotificationManager, NotificationType, NotificationPriority


T = TypeVar('T')

def get_default_value(name: str, value: T) -> T:
    """
    Load setting value from .env with A0_SET_ prefix, falling back to default.

    Args:
        name: Setting name (will be prefixed with A0_SET_)
        value: Default value to use if env var not set

    Returns:
        Environment variable value (type-normalized) or default value
    """
    env_value = dotenv.get_dotenv_value(f"A0_SET_{name}", dotenv.get_dotenv_value(f"A0_SET_{name.upper()}", None))

    if env_value is None:
        return value

    # Normalize type to match value param type
    try:
        if isinstance(value, bool):
            return env_value.strip().lower() in ('true', '1', 'yes', 'on')  # type: ignore
        elif isinstance(value, dict):
            return json.loads(env_value.strip())  # type: ignore
        elif isinstance(value, str):
            return str(env_value).strip()  # type: ignore
        else:
            return type(value)(env_value.strip())  # type: ignore
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        PrintStyle(background_color="yellow", font_color="black").print(
            f"Warning: Invalid value for A0_SET_{name}='{env_value}': {e}. Using default: {value}"
        )
        return value

class Settings(TypedDict):
    version: str

    chat_model_provider: str
    chat_model_name: str
    chat_model_api_base: str
    chat_model_kwargs: dict[str, Any]
    chat_model_ctx_length: int
    chat_model_ctx_history: float
    chat_model_vision: bool
    chat_model_rl_requests: int
    chat_model_rl_input: int
    chat_model_rl_output: int

    util_model_provider: str
    util_model_name: str
    util_model_api_base: str
    util_model_kwargs: dict[str, Any]
    util_model_ctx_length: int
    util_model_ctx_input: float
    util_model_rl_requests: int
    util_model_rl_input: int
    util_model_rl_output: int

    embed_model_provider: str
    embed_model_name: str
    embed_model_api_base: str
    embed_model_kwargs: dict[str, Any]
    embed_model_rl_requests: int
    embed_model_rl_input: int

    browser_model_provider: str
    browser_model_name: str
    browser_model_api_base: str
    browser_model_vision: bool
    browser_model_rl_requests: int
    browser_model_rl_input: int
    browser_model_rl_output: int
    browser_model_kwargs: dict[str, Any]
    browser_http_headers: dict[str, Any]
    browser_max_steps: int
    browser_backend: str

    subagent_model_provider: str
    subagent_model_name: str
    subagent_model_api_base: str
    subagent_model_kwargs: dict[str, Any]
    subagent_model_ctx_length: int
    subagent_model_rl_requests: int
    subagent_model_rl_input: int
    subagent_model_rl_output: int

    agent_profile: str
    agent_memory_subdir: str
    agent_knowledge_subdir: str

    workdir_path: str
    workdir_show: bool
    workdir_max_depth: int
    workdir_max_files: int
    workdir_max_folders: int
    workdir_max_lines: int
    workdir_gitignore: str

    memory_recall_enabled: bool
    memory_recall_delayed: bool
    memory_recall_interval: int
    memory_recall_history_len: int
    memory_recall_memories_max_search: int
    memory_recall_solutions_max_search: int
    memory_recall_memories_max_result: int
    memory_recall_solutions_max_result: int
    memory_recall_similarity_threshold: float
    memory_recall_query_prep: bool
    memory_recall_post_filter: bool
    memory_memorize_enabled: bool
    memory_memorize_consolidation: bool
    memory_memorize_replace_threshold: float

    api_keys: dict[str, str]

    auth_login: str
    auth_password: str
    root_password: str

    rfc_auto_docker: bool
    rfc_url: str
    rfc_password: str
    rfc_port_http: int
    rfc_port_ssh: int

    shell_interface: Literal['local','ssh']
    websocket_server_restart_enabled: bool
    uvicorn_access_logs_enabled: bool

    stt_model_size: str
    stt_language: str
    stt_silence_threshold: float
    stt_silence_duration: int
    stt_waiting_timeout: int

    tts_kokoro: bool

    mcp_servers: str
    mcp_client_init_timeout: int
    mcp_client_tool_timeout: int
    mcp_server_enabled: bool
    mcp_server_token: str

    a2a_server_enabled: bool

    # Swarm orchestration
    swarm_enabled: bool
    swarm_default_type: str
    swarm_default_model: str
    swarm_max_agents: int
    swarm_max_loops: int
    swarm_timeout: int
    swarm_track_tokens: bool
    swarm_agent_manifests: str
    swarm_dynamic_reassignment: bool
    swarm_output_format: str
    swarm_tier_premium_enabled: bool
    swarm_tier_premium_provider: str
    swarm_tier_premium_name: str
    swarm_tier_premium_api_base: str
    swarm_tier_mid_enabled: bool
    swarm_tier_mid_provider: str
    swarm_tier_mid_name: str
    swarm_tier_mid_api_base: str
    swarm_tier_low_enabled: bool
    swarm_tier_low_provider: str
    swarm_tier_low_name: str
    swarm_tier_low_api_base: str

    # Plugin system
    plugins_enabled: bool
    plugin_discord_enabled: bool
    plugin_discord_bot_token: str
    plugin_discord_owner_id: str
    plugin_discord_command_prefix: str
    plugin_discord_respond_dms: bool
    plugin_discord_respond_mentions: bool

    # Telegram plugin
    plugin_telegram_enabled: bool
    plugin_telegram_bot_token: str
    plugin_telegram_allowed_users: str
    plugin_telegram_respond_groups: bool
    plugin_telegram_respond_private: bool

    # Slack plugin
    plugin_slack_enabled: bool
    plugin_slack_bot_token: str
    plugin_slack_app_token: str
    plugin_slack_signing_secret: str
    plugin_slack_allowed_channels: str
    plugin_slack_respond_dms: bool
    plugin_slack_respond_mentions: bool

    # Teams plugin
    plugin_teams_enabled: bool
    plugin_teams_app_id: str
    plugin_teams_app_password: str

    # WhatsApp plugin
    plugin_whatsapp_enabled: bool
    plugin_whatsapp_session_name: str
    plugin_whatsapp_allowed_numbers: str

    # Webhook plugin
    plugin_webhook_enabled: bool
    plugin_webhook_path: str
    plugin_webhook_auth_token: str

    # Email plugin
    plugin_email_enabled: bool
    plugin_email_imap_host: str
    plugin_email_imap_port: int
    plugin_email_imap_user: str
    plugin_email_imap_password: str
    plugin_email_smtp_host: str
    plugin_email_smtp_port: int
    plugin_email_smtp_user: str
    plugin_email_smtp_password: str
    plugin_email_use_tls: bool
    plugin_email_poll_interval: int
    plugin_email_allowed_senders: str

    # ElevenLabs TTS
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    elevenlabs_model_id: str
    tts_provider: str

    # Model failover
    model_failover_enabled: bool
    model_failover_providers: str

    # Air-gapped mode
    air_gapped_mode: bool

    # --- OpenClaw Feature Adoption ---
    # Lifecycle reactions
    lifecycle_reactions_enabled: bool
    lifecycle_reactions_emoji_set: str  # "default" | "minimal" | "custom"

    # Nested sub-agents
    subagent_enabled: bool
    subagent_max_depth: int
    subagent_max_children: int

    # DM access control
    dm_policy_mode: str  # "all" | "allowlist" | "owner_only" | "none"
    dm_policy_allowlist: str  # comma-separated user IDs

    # Per-channel model overrides
    model_override_discord: str
    model_override_telegram: str
    model_override_slack: str

    # Sandbox browser isolation
    sandbox_browser_binds: str
    sandbox_browser_read_only: bool
    sandbox_browser_network: str  # "bridge" | "host" | "none"

    # Cron webhook delivery
    cron_webhook_enabled: bool
    cron_webhook_default_url: str
    cron_webhook_auth_token: str

    # WebMCP (Web Model Context Protocol) support
    webmcp_enabled: bool

    # Cloudflare Workers AI credentials
    cloudflare_account_id: str
    cloudflare_api_token: str

    variables: str
    secrets: str

    # LiteLLM global kwargs applied to all model calls
    litellm_global_kwargs: dict[str, Any]

    update_check_enabled: bool

    # Skills auto-load
    auto_load_skills: str


class PartialSettings(Settings, total=False):
    pass


class FieldOption(TypedDict):
    value: str
    label: str

class SettingsField(TypedDict, total=False):
    id: str
    title: str
    description: str
    type: Literal[
        "text",
        "number",
        "select",
        "range",
        "textarea",
        "password",
        "switch",
        "button",
        "html",
    ]
    value: Any
    min: float
    max: float
    step: float
    hidden: bool
    options: list[FieldOption]
    style: str


class SettingsSection(TypedDict, total=False):
    id: str
    title: str
    description: str
    fields: list[SettingsField]
    tab: str  # Indicates which tab this section belongs to

class ModelProvider(ProvidersFO):
    pass

class SettingsOutputAdditional(TypedDict):
    chat_providers: list[ModelProvider]
    embedding_providers: list[ModelProvider]
    shell_interfaces: list[FieldOption]
    agent_subdirs: list[FieldOption]
    knowledge_subdirs: list[FieldOption]
    stt_models: list[FieldOption]
    is_dockerized: bool
    runtime_settings: dict[str, Any]


class SettingsOutput(TypedDict):
    settings: Settings
    additional: SettingsOutputAdditional


PASSWORD_PLACEHOLDER = "****PSWD****"
API_KEY_PLACEHOLDER = "************"

SETTINGS_FILE = files.get_abs_path("usr/settings.json")
_settings: Settings | None = None
_runtime_settings_snapshot: Settings | None = None

OptionT = TypeVar("OptionT", bound=FieldOption)

def _ensure_option_present(options: list[OptionT] | None, current_value: str | None) -> list[OptionT]:
    """
    Ensure the currently selected value exists in a dropdown options list.
    If missing, inserts it at the front as {value: current_value, label: current_value}.
    """
    opts = list(options or [])
    if not current_value:
        return opts
    for o in opts:
        if o.get("value") == current_value:
            return opts
    opts.insert(0, cast(OptionT, {"value": current_value, "label": current_value}))
    return opts

def convert_out(settings: Settings) -> SettingsOutput:
    out = SettingsOutput(
        settings = settings.copy(),
        additional = SettingsOutputAdditional(
            chat_providers=get_providers("chat"),
            embedding_providers=get_providers("embedding"),
            shell_interfaces=[{"value": "local", "label": "Local Python TTY"}, {"value": "ssh", "label": "SSH"}],
            is_dockerized=runtime.is_dockerized(),
            agent_subdirs=[{"value": subdir, "label": subdir}
                for subdir in files.get_subdirectories("agents")
                if subdir != "_example"],
            knowledge_subdirs=[{"value": subdir, "label": subdir}
                for subdir in files.get_subdirectories("knowledge", exclude="default")],
            stt_models=[
                {"value": "tiny", "label": "Tiny (39M, English)"},
                {"value": "base", "label": "Base (74M, English)"},
                {"value": "small", "label": "Small (244M, English)"},
                {"value": "medium", "label": "Medium (769M, English)"},
                {"value": "large", "label": "Large (1.5B, Multilingual)"},
                {"value": "turbo", "label": "Turbo (Multilingual)"},
            ],
            runtime_settings={},
        ),
    )

    # ensure dropdown options include currently selected values
    additional = out["additional"]
    current = out["settings"]

    default_settings = get_default_settings()
    runtime_settings = _runtime_settings_snapshot or settings
    additional["runtime_settings"] = {
        "uvicorn_access_logs_enabled": bool(
            runtime_settings.get(
                "uvicorn_access_logs_enabled",
                default_settings["uvicorn_access_logs_enabled"],
            )
        ),
    }

    additional["chat_providers"] = _ensure_option_present(additional.get("chat_providers"), current.get("chat_model_provider"))
    additional["chat_providers"] = _ensure_option_present(additional.get("chat_providers"), current.get("util_model_provider"))
    additional["chat_providers"] = _ensure_option_present(additional.get("chat_providers"), current.get("browser_model_provider"))
    additional["chat_providers"] = _ensure_option_present(additional.get("chat_providers"), current.get("subagent_model_provider"))
    additional["chat_providers"] = _ensure_option_present(additional.get("chat_providers"), current.get("swarm_tier_premium_provider"))
    additional["chat_providers"] = _ensure_option_present(additional.get("chat_providers"), current.get("swarm_tier_mid_provider"))
    additional["chat_providers"] = _ensure_option_present(additional.get("chat_providers"), current.get("swarm_tier_low_provider"))
    additional["embedding_providers"] = _ensure_option_present(additional.get("embedding_providers"), current.get("embed_model_provider"))
    additional["shell_interfaces"] = _ensure_option_present(additional.get("shell_interfaces"), current.get("shell_interface"))
    additional["agent_subdirs"] = _ensure_option_present(additional.get("agent_subdirs"), current.get("agent_profile"))
    additional["knowledge_subdirs"] = _ensure_option_present(additional.get("knowledge_subdirs"), current.get("agent_knowledge_subdir"))
    additional["stt_models"] = _ensure_option_present(additional.get("stt_models"), current.get("stt_model_size"))

    # masked api keys
    providers = get_providers("chat") + get_providers("embedding")
    for provider in providers:
        provider_name = provider["value"]
        api_key = settings["api_keys"].get(provider_name, models.get_api_key(provider_name))
        settings["api_keys"][provider_name] = API_KEY_PLACEHOLDER if api_key and api_key != "None" else ""

    # load auth from dotenv
    out["settings"]["auth_login"] = dotenv.get_dotenv_value(dotenv.KEY_AUTH_LOGIN) or ""
    out["settings"]["auth_password"] = (
        PASSWORD_PLACEHOLDER if dotenv.get_dotenv_value(dotenv.KEY_AUTH_PASSWORD) else ""
    )
    out["settings"]["rfc_password"] = (
        PASSWORD_PLACEHOLDER if dotenv.get_dotenv_value(dotenv.KEY_RFC_PASSWORD) else ""
    )
    out["settings"]["root_password"] = (
        PASSWORD_PLACEHOLDER if dotenv.get_dotenv_value(dotenv.KEY_ROOT_PASSWORD) else ""
    )

    # mask plugin discord bot token
    discord_token = dotenv.get_dotenv_value("DISCORD_BOT_TOKEN") or current.get("plugin_discord_bot_token", "")
    out["settings"]["plugin_discord_bot_token"] = PASSWORD_PLACEHOLDER if discord_token else ""

    # mask telegram bot token
    tg_token = dotenv.get_dotenv_value("TELEGRAM_BOT_TOKEN") or current.get("plugin_telegram_bot_token", "")
    out["settings"]["plugin_telegram_bot_token"] = PASSWORD_PLACEHOLDER if tg_token else ""

    # mask slack tokens
    slack_bot = dotenv.get_dotenv_value("SLACK_BOT_TOKEN") or current.get("plugin_slack_bot_token", "")
    out["settings"]["plugin_slack_bot_token"] = PASSWORD_PLACEHOLDER if slack_bot else ""
    slack_app = dotenv.get_dotenv_value("SLACK_APP_TOKEN") or current.get("plugin_slack_app_token", "")
    out["settings"]["plugin_slack_app_token"] = PASSWORD_PLACEHOLDER if slack_app else ""
    slack_secret = dotenv.get_dotenv_value("SLACK_SIGNING_SECRET") or current.get("plugin_slack_signing_secret", "")
    out["settings"]["plugin_slack_signing_secret"] = PASSWORD_PLACEHOLDER if slack_secret else ""

    # mask teams credentials
    teams_pwd = dotenv.get_dotenv_value("TEAMS_APP_PASSWORD") or current.get("plugin_teams_app_password", "")
    out["settings"]["plugin_teams_app_password"] = PASSWORD_PLACEHOLDER if teams_pwd else ""

    # mask webhook auth token
    wh_token = dotenv.get_dotenv_value("WEBHOOK_AUTH_TOKEN") or current.get("plugin_webhook_auth_token", "")
    out["settings"]["plugin_webhook_auth_token"] = PASSWORD_PLACEHOLDER if wh_token else ""

    # mask email passwords
    email_imap_pw = dotenv.get_dotenv_value("EMAIL_IMAP_PASSWORD") or current.get("plugin_email_imap_password", "")
    out["settings"]["plugin_email_imap_password"] = PASSWORD_PLACEHOLDER if email_imap_pw else ""
    email_smtp_pw = dotenv.get_dotenv_value("EMAIL_SMTP_PASSWORD") or current.get("plugin_email_smtp_password", "")
    out["settings"]["plugin_email_smtp_password"] = PASSWORD_PLACEHOLDER if email_smtp_pw else ""

    # mask elevenlabs api key
    el_key = dotenv.get_dotenv_value("ELEVENLABS_API_KEY") or current.get("elevenlabs_api_key", "")
    out["settings"]["elevenlabs_api_key"] = PASSWORD_PLACEHOLDER if el_key else ""

    # mask cloudflare credentials
    cf_account = dotenv.get_dotenv_value("CLOUDFLARE_ACCOUNT_ID") or current.get("cloudflare_account_id", "")
    out["settings"]["cloudflare_account_id"] = PASSWORD_PLACEHOLDER if cf_account else ""
    cf_token = dotenv.get_dotenv_value("CLOUDFLARE_API_TOKEN") or current.get("cloudflare_api_token", "")
    out["settings"]["cloudflare_api_token"] = PASSWORD_PLACEHOLDER if cf_token else ""

    #secrets
    secrets_manager = get_default_secrets_manager()
    try:
        out["settings"]["secrets"] = secrets_manager.get_masked_secrets()
    except Exception:
        out["settings"]["secrets"] = ""

    # mask API keys before sending to frontend
    if isinstance(out["settings"].get("api_keys"), dict):
        for provider, value in list(out["settings"]["api_keys"].items()):
            if value:
                out["settings"]["api_keys"][provider] = API_KEY_PLACEHOLDER

    # normalize certain fields
    for key, value in list(out["settings"].items()):
        # convert kwargs dicts to .env format
        if (key.endswith("_kwargs") or key=="browser_http_headers") and isinstance(value, dict):
            out["settings"][key] = _dict_to_env(value)
    return out

def _get_api_key_field(settings: Settings, provider: str, title: str) -> SettingsField:
    key = settings["api_keys"].get(provider, models.get_api_key(provider))
    # For API keys, use simple asterisk placeholder for existing keys
    return {
        "id": f"api_key_{provider}",
        "title": title,
        "type": "text",
        "value": (API_KEY_PLACEHOLDER if key and key != "None" else ""),
    }


def convert_in(settings: Settings) -> Settings:
    current = get_settings()

    for key, value in settings.items():
        # Special handling for browser_http_headers and *_kwargs (stored as .env text)
        if (key == "browser_http_headers" or key.endswith("_kwargs")) and isinstance(value, str):
            current[key] = _env_to_dict(value)
            continue

        current[key] = value
    return current


def get_settings() -> Settings:
    global _settings
    if not _settings:
        _settings = _read_settings_file()
    if not _settings:
        _settings = get_default_settings()
    norm = normalize_settings(_settings)
    _load_sensitive_settings(norm)
    return norm


def reload_settings() -> Settings:
    global _settings
    _settings = None
    return get_settings()


def set_runtime_settings_snapshot(settings: Settings) -> None:
    global _runtime_settings_snapshot
    _runtime_settings_snapshot = settings.copy()


def set_settings(settings: Settings, apply: bool = True):
    global _settings
    previous = _settings
    _settings = normalize_settings(settings)
    _write_settings_file(_settings)
    if apply:
        _apply_settings(previous)
    return reload_settings()


def set_settings_delta(delta: dict, apply: bool = True):
    current = get_settings()
    new = {**current, **delta}
    return set_settings(new, apply)  # type: ignore


def merge_settings(original: Settings, delta: dict) -> Settings:
    merged = original.copy()
    merged.update(delta)
    return merged


def normalize_settings(settings: Settings) -> Settings:
    copy = settings.copy()
    default = get_default_settings()

    # adjust settings values to match current version if needed
    if "version" not in copy or copy["version"] != default["version"]:
        _adjust_to_version(copy, default)
        copy["version"] = default["version"]  # sync version

    # remove keys that are not in default
    keys_to_remove = [key for key in copy if key not in default]
    for key in keys_to_remove:
        del copy[key]

    # add missing keys and normalize types
    for key, value in default.items():
        if key not in copy:
            copy[key] = value
        else:
            try:
                copy[key] = type(value)(copy[key])  # type: ignore
                if isinstance(copy[key], str):
                    copy[key] = copy[key].strip()  # strip strings
            except (ValueError, TypeError):
                copy[key] = value  # make default instead

    # mcp server token is set automatically
    copy["mcp_server_token"] = create_auth_token()

    return copy


def _adjust_to_version(settings: Settings, default: Settings):
    # starting with 0.9, the default prompt subfolder for agent no. 0 is agent0
    # switch to agent0 if the old default is used from v0.8
    if "version" not in settings or settings["version"].startswith("v0.8"):
        if "agent_profile" not in settings or settings["agent_profile"] == "default":
            settings["agent_profile"] = "agent0"



def _load_sensitive_settings(settings: Settings):
    # load api keys from .env
    providers = get_providers("chat") + get_providers("embedding")
    for provider in providers:
        provider_name = provider["value"]
        api_key = settings["api_keys"].get(provider_name) or models.get_api_key(provider_name)
        if api_key and api_key != "None":
            settings["api_keys"][provider_name] = api_key

    # load auth fields from .env
    settings["auth_login"] = dotenv.get_dotenv_value(dotenv.KEY_AUTH_LOGIN) or ""
    settings["auth_password"] = dotenv.get_dotenv_value(dotenv.KEY_AUTH_PASSWORD) or ""
    settings["rfc_password"] = dotenv.get_dotenv_value(dotenv.KEY_RFC_PASSWORD) or ""
    settings["root_password"] = dotenv.get_dotenv_value(dotenv.KEY_ROOT_PASSWORD) or ""

    # load plugin tokens from .env
    settings["plugin_telegram_bot_token"] = dotenv.get_dotenv_value("TELEGRAM_BOT_TOKEN") or ""
    settings["plugin_slack_bot_token"] = dotenv.get_dotenv_value("SLACK_BOT_TOKEN") or ""
    settings["plugin_slack_app_token"] = dotenv.get_dotenv_value("SLACK_APP_TOKEN") or ""
    settings["plugin_slack_signing_secret"] = dotenv.get_dotenv_value("SLACK_SIGNING_SECRET") or ""
    settings["plugin_teams_app_password"] = dotenv.get_dotenv_value("TEAMS_APP_PASSWORD") or ""
    settings["plugin_webhook_auth_token"] = dotenv.get_dotenv_value("WEBHOOK_AUTH_TOKEN") or ""
    settings["plugin_email_imap_password"] = dotenv.get_dotenv_value("EMAIL_IMAP_PASSWORD") or ""
    settings["plugin_email_smtp_password"] = dotenv.get_dotenv_value("EMAIL_SMTP_PASSWORD") or ""
    settings["elevenlabs_api_key"] = dotenv.get_dotenv_value("ELEVENLABS_API_KEY") or ""

    # load cloudflare credentials from .env
    settings["cloudflare_account_id"] = dotenv.get_dotenv_value("CLOUDFLARE_ACCOUNT_ID") or ""
    settings["cloudflare_api_token"] = dotenv.get_dotenv_value("CLOUDFLARE_API_TOKEN") or ""

    # load secrets raw content
    secrets_manager = get_default_secrets_manager()
    try:
        settings["secrets"] = secrets_manager.read_secrets_raw()
    except Exception:
        settings["secrets"] = ""


def _read_settings_file() -> Settings | None:
    if os.path.exists(SETTINGS_FILE):
        content = files.read_file(SETTINGS_FILE)
        parsed = json.loads(content)
        return normalize_settings(parsed)


def _write_settings_file(settings: Settings):
    settings = settings.copy()
    _write_sensitive_settings(settings)
    _remove_sensitive_settings(settings)

    # write settings
    content = json.dumps(settings, indent=4)
    files.write_file(SETTINGS_FILE, content)


def _remove_sensitive_settings(settings: Settings):
    settings["api_keys"] = {}
    settings["auth_login"] = ""
    settings["auth_password"] = ""
    settings["rfc_password"] = ""
    settings["root_password"] = ""
    settings["mcp_server_token"] = ""
    settings["secrets"] = ""
    settings["plugin_discord_bot_token"] = ""
    settings["plugin_telegram_bot_token"] = ""
    settings["plugin_slack_bot_token"] = ""
    settings["plugin_slack_app_token"] = ""
    settings["plugin_slack_signing_secret"] = ""
    settings["plugin_teams_app_password"] = ""
    settings["plugin_webhook_auth_token"] = ""
    settings["plugin_email_imap_password"] = ""
    settings["plugin_email_smtp_password"] = ""
    settings["elevenlabs_api_key"] = ""
    settings["cloudflare_account_id"] = ""
    settings["cloudflare_api_token"] = ""


def _write_sensitive_settings(settings: Settings):
    for key, val in settings["api_keys"].items():
        if val != API_KEY_PLACEHOLDER:
            dotenv.save_dotenv_value(f"API_KEY_{key.upper()}", val)

    dotenv.save_dotenv_value(dotenv.KEY_AUTH_LOGIN, settings["auth_login"])
    if settings["auth_password"] != PASSWORD_PLACEHOLDER:
        dotenv.save_dotenv_value(dotenv.KEY_AUTH_PASSWORD, settings["auth_password"])
    if settings["rfc_password"] != PASSWORD_PLACEHOLDER:
        dotenv.save_dotenv_value(dotenv.KEY_RFC_PASSWORD, settings["rfc_password"])
    if settings["root_password"] != PASSWORD_PLACEHOLDER:
        if runtime.is_dockerized():
            dotenv.save_dotenv_value(dotenv.KEY_ROOT_PASSWORD, settings["root_password"])
            set_root_password(settings["root_password"])

    # Handle secrets separately - merge with existing preserving comments/order and support deletions
    secrets_manager = get_default_secrets_manager()
    submitted_content = settings["secrets"]
    secrets_manager.save_secrets_with_merge(submitted_content)

    # Discord bot token
    if settings.get("plugin_discord_bot_token") and settings["plugin_discord_bot_token"] != PASSWORD_PLACEHOLDER:
        dotenv.save_dotenv_value("DISCORD_BOT_TOKEN", settings["plugin_discord_bot_token"])

    # Telegram bot token
    if settings.get("plugin_telegram_bot_token") and settings["plugin_telegram_bot_token"] != PASSWORD_PLACEHOLDER:
        dotenv.save_dotenv_value("TELEGRAM_BOT_TOKEN", settings["plugin_telegram_bot_token"])

    # Slack tokens
    if settings.get("plugin_slack_bot_token") and settings["plugin_slack_bot_token"] != PASSWORD_PLACEHOLDER:
        dotenv.save_dotenv_value("SLACK_BOT_TOKEN", settings["plugin_slack_bot_token"])
    if settings.get("plugin_slack_app_token") and settings["plugin_slack_app_token"] != PASSWORD_PLACEHOLDER:
        dotenv.save_dotenv_value("SLACK_APP_TOKEN", settings["plugin_slack_app_token"])
    if settings.get("plugin_slack_signing_secret") and settings["plugin_slack_signing_secret"] != PASSWORD_PLACEHOLDER:
        dotenv.save_dotenv_value("SLACK_SIGNING_SECRET", settings["plugin_slack_signing_secret"])

    # Teams credentials
    if settings.get("plugin_teams_app_password") and settings["plugin_teams_app_password"] != PASSWORD_PLACEHOLDER:
        dotenv.save_dotenv_value("TEAMS_APP_PASSWORD", settings["plugin_teams_app_password"])

    # Webhook auth token
    if settings.get("plugin_webhook_auth_token") and settings["plugin_webhook_auth_token"] != PASSWORD_PLACEHOLDER:
        dotenv.save_dotenv_value("WEBHOOK_AUTH_TOKEN", settings["plugin_webhook_auth_token"])

    # Email passwords
    if settings.get("plugin_email_imap_password") and settings["plugin_email_imap_password"] != PASSWORD_PLACEHOLDER:
        dotenv.save_dotenv_value("EMAIL_IMAP_PASSWORD", settings["plugin_email_imap_password"])
    if settings.get("plugin_email_smtp_password") and settings["plugin_email_smtp_password"] != PASSWORD_PLACEHOLDER:
        dotenv.save_dotenv_value("EMAIL_SMTP_PASSWORD", settings["plugin_email_smtp_password"])

    # ElevenLabs API key
    if settings.get("elevenlabs_api_key") and settings["elevenlabs_api_key"] != PASSWORD_PLACEHOLDER:
        dotenv.save_dotenv_value("ELEVENLABS_API_KEY", settings["elevenlabs_api_key"])

    # Cloudflare credentials
    if settings.get("cloudflare_account_id") and settings["cloudflare_account_id"] != PASSWORD_PLACEHOLDER:
        dotenv.save_dotenv_value("CLOUDFLARE_ACCOUNT_ID", settings["cloudflare_account_id"])
    if settings.get("cloudflare_api_token") and settings["cloudflare_api_token"] != PASSWORD_PLACEHOLDER:
        dotenv.save_dotenv_value("CLOUDFLARE_API_TOKEN", settings["cloudflare_api_token"])



def get_default_settings() -> Settings:
    gitignore = files.read_file(files.get_abs_path("conf/workdir.gitignore"))
    return Settings(
        version=_get_version(),
        chat_model_provider=get_default_value("chat_model_provider", "openrouter"),
        chat_model_name=get_default_value("chat_model_name", "anthropic/claude-sonnet-4.6"),
        chat_model_api_base=get_default_value("chat_model_api_base", ""),
        chat_model_kwargs=get_default_value("chat_model_kwargs", {}),
        chat_model_ctx_length=get_default_value("chat_model_ctx_length", 100000),
        chat_model_ctx_history=get_default_value("chat_model_ctx_history", 0.7),
        chat_model_vision=get_default_value("chat_model_vision", True),
        chat_model_rl_requests=get_default_value("chat_model_rl_requests", 0),
        chat_model_rl_input=get_default_value("chat_model_rl_input", 0),
        chat_model_rl_output=get_default_value("chat_model_rl_output", 0),
        util_model_provider=get_default_value("util_model_provider", "openrouter"),
        util_model_name=get_default_value("util_model_name", "google/gemini-3-flash-preview"),
        util_model_api_base=get_default_value("util_model_api_base", ""),
        util_model_ctx_length=get_default_value("util_model_ctx_length", 100000),
        util_model_ctx_input=get_default_value("util_model_ctx_input", 0.7),
        util_model_kwargs=get_default_value("util_model_kwargs", {}),
        util_model_rl_requests=get_default_value("util_model_rl_requests", 0),
        util_model_rl_input=get_default_value("util_model_rl_input", 0),
        util_model_rl_output=get_default_value("util_model_rl_output", 0),
        embed_model_provider=get_default_value("embed_model_provider", "huggingface"),
        embed_model_name=get_default_value("embed_model_name", "sentence-transformers/all-MiniLM-L6-v2"),
        embed_model_api_base=get_default_value("embed_model_api_base", ""),
        embed_model_kwargs=get_default_value("embed_model_kwargs", {}),
        embed_model_rl_requests=get_default_value("embed_model_rl_requests", 0),
        embed_model_rl_input=get_default_value("embed_model_rl_input", 0),
        browser_model_provider=get_default_value("browser_model_provider", "openrouter"),
        browser_model_name=get_default_value("browser_model_name", "anthropic/claude-sonnet-4.6"),
        browser_model_api_base=get_default_value("browser_model_api_base", ""),
        browser_model_vision=get_default_value("browser_model_vision", True),
        browser_model_rl_requests=get_default_value("browser_model_rl_requests", 0),
        browser_model_rl_input=get_default_value("browser_model_rl_input", 0),
        browser_model_rl_output=get_default_value("browser_model_rl_output", 0),
        browser_model_kwargs=get_default_value("browser_model_kwargs", {}),
        browser_http_headers=get_default_value("browser_http_headers", {}),
        browser_max_steps=get_default_value("browser_max_steps", 25),
        browser_backend=get_default_value("browser_backend", "browser_use"),
        subagent_model_provider=get_default_value("subagent_model_provider", ""),
        subagent_model_name=get_default_value("subagent_model_name", ""),
        subagent_model_api_base=get_default_value("subagent_model_api_base", ""),
        subagent_model_kwargs=get_default_value("subagent_model_kwargs", {}),
        subagent_model_ctx_length=get_default_value("subagent_model_ctx_length", 0),
        subagent_model_rl_requests=get_default_value("subagent_model_rl_requests", 0),
        subagent_model_rl_input=get_default_value("subagent_model_rl_input", 0),
        subagent_model_rl_output=get_default_value("subagent_model_rl_output", 0),
        memory_recall_enabled=get_default_value("memory_recall_enabled", True),
        memory_recall_delayed=get_default_value("memory_recall_delayed", False),
        memory_recall_interval=get_default_value("memory_recall_interval", 3),
        memory_recall_history_len=get_default_value("memory_recall_history_len", 10000),
        memory_recall_memories_max_search=get_default_value("memory_recall_memories_max_search", 12),
        memory_recall_solutions_max_search=get_default_value("memory_recall_solutions_max_search", 8),
        memory_recall_memories_max_result=get_default_value("memory_recall_memories_max_result", 5),
        memory_recall_solutions_max_result=get_default_value("memory_recall_solutions_max_result", 3),
        memory_recall_similarity_threshold=get_default_value("memory_recall_similarity_threshold", 0.7),
        memory_recall_query_prep=get_default_value("memory_recall_query_prep", False),
        memory_recall_post_filter=get_default_value("memory_recall_post_filter", False),
        memory_memorize_enabled=get_default_value("memory_memorize_enabled", True),
        memory_memorize_consolidation=get_default_value("memory_memorize_consolidation", True),
        memory_memorize_replace_threshold=get_default_value("memory_memorize_replace_threshold", 0.9),
        api_keys={},
        auth_login="",
        auth_password="",
        root_password="",
        agent_profile=get_default_value("agent_profile", "agent0"),
        agent_memory_subdir=get_default_value("agent_memory_subdir", "default"),
        agent_knowledge_subdir=get_default_value("agent_knowledge_subdir", "custom"),
        workdir_path=get_default_value("workdir_path", files.get_abs_path_dockerized("usr/workdir")),
        workdir_show=get_default_value("workdir_show", True),
        workdir_max_depth=get_default_value("workdir_max_depth", 5),
        workdir_max_files=get_default_value("workdir_max_files", 20),
        workdir_max_folders=get_default_value("workdir_max_folders", 20),
        workdir_max_lines=get_default_value("workdir_max_lines", 250),
        workdir_gitignore=get_default_value("workdir_gitignore", gitignore),
        rfc_auto_docker=get_default_value("rfc_auto_docker", True),
        rfc_url=get_default_value("rfc_url", "localhost"),
        rfc_password="",
        rfc_port_http=get_default_value("rfc_port_http", 55080),
        rfc_port_ssh=get_default_value("rfc_port_ssh", 55022),
        shell_interface=get_default_value("shell_interface", "local" if runtime.is_dockerized() else "ssh"),
        websocket_server_restart_enabled=get_default_value("websocket_server_restart_enabled", True),
        uvicorn_access_logs_enabled=get_default_value("uvicorn_access_logs_enabled", False),
        stt_model_size=get_default_value("stt_model_size", "base"),
        stt_language=get_default_value("stt_language", "en"),
        stt_silence_threshold=get_default_value("stt_silence_threshold", 0.3),
        stt_silence_duration=get_default_value("stt_silence_duration", 1000),
        stt_waiting_timeout=get_default_value("stt_waiting_timeout", 2000),
        tts_kokoro=get_default_value("tts_kokoro", True),
        mcp_servers=get_default_value("mcp_servers", '{\n    "mcpServers": {}\n}'),
        mcp_client_init_timeout=get_default_value("mcp_client_init_timeout", 10),
        mcp_client_tool_timeout=get_default_value("mcp_client_tool_timeout", 120),
        mcp_server_enabled=get_default_value("mcp_server_enabled", False),
        mcp_server_token=create_auth_token(),
        a2a_server_enabled=get_default_value("a2a_server_enabled", False),
        swarm_enabled=get_default_value("swarm_enabled", True),
        swarm_default_type=get_default_value("swarm_default_type", "sequential"),
        swarm_default_model=get_default_value("swarm_default_model", ""),
        swarm_max_agents=get_default_value("swarm_max_agents", 10),
        swarm_max_loops=get_default_value("swarm_max_loops", 3),
        swarm_timeout=get_default_value("swarm_timeout", 300),
        swarm_track_tokens=get_default_value("swarm_track_tokens", True),
        swarm_agent_manifests=get_default_value("swarm_agent_manifests", "[]"),
        swarm_dynamic_reassignment=get_default_value("swarm_dynamic_reassignment", False),
        swarm_output_format=get_default_value("swarm_output_format", "markdown"),
        swarm_tier_premium_enabled=get_default_value("swarm_tier_premium_enabled", True),
        swarm_tier_premium_provider=get_default_value("swarm_tier_premium_provider", "openrouter"),
        swarm_tier_premium_name=get_default_value("swarm_tier_premium_name", "anthropic/claude-sonnet-4-20250514"),
        swarm_tier_premium_api_base=get_default_value("swarm_tier_premium_api_base", ""),
        swarm_tier_mid_enabled=get_default_value("swarm_tier_mid_enabled", True),
        swarm_tier_mid_provider=get_default_value("swarm_tier_mid_provider", "openrouter"),
        swarm_tier_mid_name=get_default_value("swarm_tier_mid_name", "openai/gpt-4o-mini"),
        swarm_tier_mid_api_base=get_default_value("swarm_tier_mid_api_base", ""),
        swarm_tier_low_enabled=get_default_value("swarm_tier_low_enabled", True),
        swarm_tier_low_provider=get_default_value("swarm_tier_low_provider", "openrouter"),
        swarm_tier_low_name=get_default_value("swarm_tier_low_name", "openai/gpt-3.5-turbo"),
        swarm_tier_low_api_base=get_default_value("swarm_tier_low_api_base", ""),
        plugins_enabled=get_default_value("plugins_enabled", True),
        plugin_discord_enabled=get_default_value("plugin_discord_enabled", False),
        plugin_discord_bot_token="",
        plugin_discord_owner_id=get_default_value("plugin_discord_owner_id", ""),
        plugin_discord_command_prefix=get_default_value("plugin_discord_command_prefix", "!a0"),
        plugin_discord_respond_dms=get_default_value("plugin_discord_respond_dms", True),
        plugin_discord_respond_mentions=get_default_value("plugin_discord_respond_mentions", True),
        # Telegram
        plugin_telegram_enabled=get_default_value("plugin_telegram_enabled", False),
        plugin_telegram_bot_token="",
        plugin_telegram_allowed_users=get_default_value("plugin_telegram_allowed_users", ""),
        plugin_telegram_respond_groups=get_default_value("plugin_telegram_respond_groups", True),
        plugin_telegram_respond_private=get_default_value("plugin_telegram_respond_private", True),
        # Slack
        plugin_slack_enabled=get_default_value("plugin_slack_enabled", False),
        plugin_slack_bot_token="",
        plugin_slack_app_token="",
        plugin_slack_signing_secret="",
        plugin_slack_allowed_channels=get_default_value("plugin_slack_allowed_channels", ""),
        plugin_slack_respond_dms=get_default_value("plugin_slack_respond_dms", True),
        plugin_slack_respond_mentions=get_default_value("plugin_slack_respond_mentions", True),
        # Teams
        plugin_teams_enabled=get_default_value("plugin_teams_enabled", False),
        plugin_teams_app_id=get_default_value("plugin_teams_app_id", ""),
        plugin_teams_app_password="",
        # WhatsApp
        plugin_whatsapp_enabled=get_default_value("plugin_whatsapp_enabled", False),
        plugin_whatsapp_session_name=get_default_value("plugin_whatsapp_session_name", "default"),
        plugin_whatsapp_allowed_numbers=get_default_value("plugin_whatsapp_allowed_numbers", ""),
        # Webhook
        plugin_webhook_enabled=get_default_value("plugin_webhook_enabled", False),
        plugin_webhook_path=get_default_value("plugin_webhook_path", "/webhook/agent"),
        plugin_webhook_auth_token="",
        # Email
        plugin_email_enabled=get_default_value("plugin_email_enabled", False),
        plugin_email_imap_host=get_default_value("plugin_email_imap_host", ""),
        plugin_email_imap_port=get_default_value("plugin_email_imap_port", 993),
        plugin_email_imap_user=get_default_value("plugin_email_imap_user", ""),
        plugin_email_imap_password="",
        plugin_email_smtp_host=get_default_value("plugin_email_smtp_host", ""),
        plugin_email_smtp_port=get_default_value("plugin_email_smtp_port", 587),
        plugin_email_smtp_user=get_default_value("plugin_email_smtp_user", ""),
        plugin_email_smtp_password="",
        plugin_email_use_tls=get_default_value("plugin_email_use_tls", True),
        plugin_email_poll_interval=get_default_value("plugin_email_poll_interval", 30),
        plugin_email_allowed_senders=get_default_value("plugin_email_allowed_senders", ""),
        # ElevenLabs TTS
        elevenlabs_api_key="",
        elevenlabs_voice_id=get_default_value("elevenlabs_voice_id", ""),
        elevenlabs_model_id=get_default_value("elevenlabs_model_id", "eleven_multilingual_v2"),
        tts_provider=get_default_value("tts_provider", "kokoro"),
        # Model failover
        model_failover_enabled=get_default_value("model_failover_enabled", False),
        model_failover_providers=get_default_value("model_failover_providers", ""),
        # Air-gapped mode
        air_gapped_mode=get_default_value("air_gapped_mode", False),
        # --- OpenClaw Feature Adoption ---
        lifecycle_reactions_enabled=get_default_value("lifecycle_reactions_enabled", True),
        lifecycle_reactions_emoji_set=get_default_value("lifecycle_reactions_emoji_set", "default"),
        subagent_enabled=get_default_value("subagent_enabled", True),
        subagent_max_depth=get_default_value("subagent_max_depth", 2),
        subagent_max_children=get_default_value("subagent_max_children", 5),
        dm_policy_mode=get_default_value("dm_policy_mode", "all"),
        dm_policy_allowlist=get_default_value("dm_policy_allowlist", ""),
        model_override_discord=get_default_value("model_override_discord", ""),
        model_override_telegram=get_default_value("model_override_telegram", ""),
        model_override_slack=get_default_value("model_override_slack", ""),
        sandbox_browser_binds=get_default_value("sandbox_browser_binds", "/tmp/browser:/tmp/browser"),
        sandbox_browser_read_only=get_default_value("sandbox_browser_read_only", True),
        sandbox_browser_network=get_default_value("sandbox_browser_network", "bridge"),
        cron_webhook_enabled=get_default_value("cron_webhook_enabled", False),
        cron_webhook_default_url=get_default_value("cron_webhook_default_url", ""),
        cron_webhook_auth_token="",
        webmcp_enabled=get_default_value("webmcp_enabled", True),
        # Cloudflare
        cloudflare_account_id="",
        cloudflare_api_token="",
        variables="",
        secrets="",
        litellm_global_kwargs=get_default_value("litellm_global_kwargs", {}),
        update_check_enabled=get_default_value("update_check_enabled", True),
        auto_load_skills=get_default_value("auto_load_skills", ""),
    )


def _apply_settings(previous: Settings | None):
    global _settings
    if _settings:
        from agent import AgentContext
        from initialize import initialize_agent

        config = initialize_agent()
        for ctx in AgentContext.all():
            ctx.config = config  # reinitialize context config with new settings
            # apply config to agents
            agent = ctx.agent0
            while agent:
                agent.config = ctx.config
                agent = agent.get_data(agent.DATA_NAME_SUBORDINATE)

        # reload whisper model if necessary
        if not previous or _settings["stt_model_size"] != previous["stt_model_size"]:
            task = defer.DeferredTask().start_task(
                whisper.preload, _settings["stt_model_size"]
            )  # TODO overkill, replace with background task

        # force memory reload on embedding model change
        if not previous or (
            _settings["embed_model_name"] != previous["embed_model_name"]
            or _settings["embed_model_provider"] != previous["embed_model_provider"]
            or _settings["embed_model_kwargs"] != previous["embed_model_kwargs"]
        ):
            from python.helpers.memory import reload as memory_reload

            memory_reload()

        # update mcp settings if necessary
        if not previous or _settings["mcp_servers"] != previous["mcp_servers"]:
            from python.helpers.mcp_handler import MCPConfig

            async def update_mcp_settings(mcp_servers: str):
                PrintStyle(
                    background_color="black", font_color="white", padding=True
                ).print("Updating MCP config...")
                NotificationManager.send_notification(
                    type=NotificationType.INFO,
                    priority=NotificationPriority.NORMAL,
                    message="Updating MCP settings...",
                    display_time=999,
                    group="settings-mcp"
                )

                mcp_config = MCPConfig.get_instance()
                try:
                    MCPConfig.update(mcp_servers)
                except Exception as e:
                    
                    NotificationManager.send_notification(
                        type=NotificationType.ERROR,
                        priority=NotificationPriority.HIGH,
                        message="Failed to update MCP settings",
                        detail=str(e),                        
                    )
                    (
                        PrintStyle(
                            background_color="red", font_color="black", padding=True
                        ).print("Failed to update MCP settings")
                    )
                    (
                        PrintStyle(
                            background_color="black", font_color="red", padding=True
                        ).print(f"{e}")
                    )

                PrintStyle(
                    background_color="#6734C3", font_color="white", padding=True
                ).print("Parsed MCP config:")
                (
                    PrintStyle(
                        background_color="#334455", font_color="white", padding=False
                    ).print(mcp_config.model_dump_json())
                )
                NotificationManager.send_notification(
                    type=NotificationType.INFO,
                    priority=NotificationPriority.NORMAL,
                    message="Finished updating MCP settings.",
                    group="settings-mcp"
                )

            task2 = defer.DeferredTask().start_task(
                update_mcp_settings, config.mcp_servers
            )  # TODO overkill, replace with background task

        # update token in mcp server
        current_token = (
            create_auth_token()
        )  # TODO - ugly, token in settings is generated from dotenv and does not always correspond
        if not previous or current_token != previous["mcp_server_token"]:

            async def update_mcp_token(token: str):
                from python.helpers.mcp_server import DynamicMcpProxy

                DynamicMcpProxy.get_instance().reconfigure(token=token)

            task3 = defer.DeferredTask().start_task(
                update_mcp_token, current_token
            )  # TODO overkill, replace with background task

        # update token in a2a server
        if not previous or current_token != previous["mcp_server_token"]:

            async def update_a2a_token(token: str):
                from python.helpers.fasta2a_server import DynamicA2AProxy

                DynamicA2AProxy.get_instance().reconfigure(token=token)

            task4 = defer.DeferredTask().start_task(
                update_a2a_token, current_token
            )  # TODO overkill, replace with background task


def _env_to_dict(data: str):
    result = {}
    for line in data.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        if '=' not in line:
            continue
            
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()
        
        # If quoted, treat as string
        if value.startswith('"') and value.endswith('"'):
            result[key] = value[1:-1].replace('\\"', '"')  # Unescape quotes
        elif value.startswith("'") and value.endswith("'"):
            result[key] = value[1:-1].replace("\\'", "'")  # Unescape quotes
        else:
            # Not quoted, try JSON parse
            try:
                result[key] = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                result[key] = value
    
    return result


def _dict_to_env(data_dict):
    lines = []
    for key, value in data_dict.items():
        if isinstance(value, str):
            # Quote strings and escape internal quotes
            escaped_value = value.replace('"', '\\"')
            lines.append(f'{key}="{escaped_value}"')
        elif isinstance(value, (dict, list, bool)) or value is None:
            # Serialize as unquoted JSON
            lines.append(f'{key}={json.dumps(value, separators=(",", ":"))}')
        else:
            # Numbers and other types as unquoted strings
            lines.append(f'{key}={value}')
    
    return "\n".join(lines)


def set_root_password(password: str):
    if not runtime.is_dockerized():
        raise Exception("root password can only be set in dockerized environments")
    _result = subprocess.run(
        ["chpasswd"],
        input=f"root:{password}".encode(),
        capture_output=True,
        check=True,
    )
    dotenv.save_dotenv_value(dotenv.KEY_ROOT_PASSWORD, password)


def get_runtime_config(set: Settings):
    if runtime.is_dockerized():
        return {
            "code_exec_ssh_enabled": set["shell_interface"] == "ssh",
            "code_exec_ssh_addr": "localhost",
            "code_exec_ssh_port": 22,
            "code_exec_ssh_user": "root",
        }
    else:
        host = set["rfc_url"]
        if "//" in host:
            host = host.split("//")[1]
        if ":" in host:
            host, port = host.split(":")
        if host.endswith("/"):
            host = host[:-1]
        return {
            "code_exec_ssh_enabled": set["shell_interface"] == "ssh",
            "code_exec_ssh_addr": host,
            "code_exec_ssh_port": set["rfc_port_ssh"],
            "code_exec_ssh_user": "root",
        }


def create_auth_token() -> str:
    runtime_id = runtime.get_persistent_id()
    username = dotenv.get_dotenv_value(dotenv.KEY_AUTH_LOGIN) or ""
    password = dotenv.get_dotenv_value(dotenv.KEY_AUTH_PASSWORD) or ""
    # use base64 encoding for a more compact token with alphanumeric chars
    hash_bytes = hashlib.sha256(f"{runtime_id}:{username}:{password}".encode()).digest()
    # encode as base64 and remove any non-alphanumeric chars (like +, /, =)
    b64_token = base64.urlsafe_b64encode(hash_bytes).decode().replace("=", "")
    return b64_token[:16]


def _get_version():
    return git.get_version()

