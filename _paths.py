"""Shared runtime path resolution for the Polymarket arbitrage system."""

import os
from pathlib import Path


PROJECT_ROOT_FALLBACK = Path(__file__).resolve().parent


def get_base_dir() -> Path:
    if env := os.environ.get("PA_BASE_DIR"):
        return Path(env)
    return PROJECT_ROOT_FALLBACK


def get_pm_trader() -> str:
    if env := os.environ.get("PM_TRADER_PATH"):
        return env

    container_path = Path("/opt/data/home/.local/bin/pm-trader")
    if container_path.exists():
        return str(container_path)

    hermes_path = Path.home() / ".hermes/home/.local/bin/pm-trader"
    if hermes_path.exists():
        return str(hermes_path)

    user_path = Path.home() / ".local/bin/pm-trader"
    if user_path.exists():
        return str(user_path)

    return "pm-trader"


def get_pm_trader_env() -> dict:
    """Return environment vars needed by the Hermes-installed pm-trader CLI."""
    env = os.environ.copy()

    hermes_home = Path.home() / ".hermes/home"
    hermes_site_packages = hermes_home / ".local/lib/python3.13/site-packages"
    if hermes_site_packages.exists():
        existing_pythonpath = env.get("PYTHONPATH")
        parts = [str(hermes_site_packages)]
        if existing_pythonpath:
            parts.append(existing_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(parts)

    hermes_pm_data = hermes_home / ".pm-trader"
    if hermes_pm_data.exists() and "PM_TRADER_DATA_DIR" not in env:
        env["PM_TRADER_DATA_DIR"] = str(hermes_pm_data)

    return env
