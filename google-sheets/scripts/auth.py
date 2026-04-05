#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from google_sheets_skill.config import load_config, save_config
from google_sheets_skill.sheets import login


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Authenticate the Google Sheets Codex skill.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure = subparsers.add_parser("configure", help="Store OAuth client config for later logins.")
    configure.add_argument("--client-secret", required=True, help="Path to the Google OAuth client JSON file.")
    configure.add_argument("--account-label", help="Optional human-friendly label for this account.")

    subparsers.add_parser("status", help="Show the stored auth configuration status.")

    login_parser = subparsers.add_parser("login", help="Open the browser OAuth flow and cache the token.")
    login_parser.add_argument("--force", action="store_true", help="Ignore any cached token and re-authenticate.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "configure":
        config = load_config()
        config["client_secret_path"] = args.client_secret
        if args.account_label:
            config["default_account_label"] = args.account_label
        save_config(config)
        print(json.dumps({"ok": True, "client_secret_path": args.client_secret}, indent=2))
        return

    if args.command == "status":
        config = load_config()
        print(
            json.dumps(
                {
                    "configured": bool(config.get("client_secret_path")),
                    "client_secret_path": config.get("client_secret_path"),
                    "token_path": config.get("token_path"),
                    "default_account_label": config.get("default_account_label"),
                    "scopes": config.get("scopes", []),
                },
                indent=2,
            )
        )
        return

    print(json.dumps(login(force=args.force), indent=2))


if __name__ == "__main__":
    main()
