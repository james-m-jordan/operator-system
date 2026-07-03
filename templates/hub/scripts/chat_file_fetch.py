#!/usr/bin/env python3
"""Fetch a chat-hosted file into local-private storage for later intake."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import load_config, relpath, resolve_root, write_json


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slugify(value: object) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value)).strip("-").lower() or "download"


def file_source_config(config: dict[str, object]) -> dict[str, object]:
    sources = config.get("file_sources", {}) if isinstance(config.get("file_sources"), dict) else {}
    chat = sources.get("chat", {}) if isinstance(sources.get("chat"), dict) else {}
    return chat


def provider_config(config: dict[str, object], provider: str) -> dict[str, object]:
    chat = file_source_config(config)
    providers = chat.get("providers", {}) if isinstance(chat.get("providers"), dict) else {}
    data = providers.get(provider, {})
    if isinstance(data, dict):
        return dict(data)
    return {"type": str(data)}


def default_provider(config: dict[str, object]) -> str:
    chat = file_source_config(config)
    return str(chat.get("default_provider", "direct-url"))


def output_path(root: Path, config: dict[str, object], args: argparse.Namespace, filename: str) -> Path:
    if args.output:
        path = Path(args.output)
        if not path.is_absolute():
            path = root / path
        return path
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    chat = file_source_config(config)
    download_root = str(chat.get("download_root", "local-private/chat-downloads"))
    return root / download_root / f"{timestamp}-{slugify(filename)}"


def filename_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    name = Path(urllib.parse.unquote(parsed.path)).name
    return name or "download.bin"


def filename_from_headers(headers: object, fallback: str) -> str:
    disposition = ""
    if hasattr(headers, "get"):
        disposition = headers.get("Content-Disposition", "")
    match = re.search(r'filename="?([^";]+)"?', disposition)
    return match.group(1) if match else fallback


def read_url(url: str, headers: dict[str, str] | None = None) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=60) as response:
        fallback = filename_from_url(response.geturl())
        filename = filename_from_headers(response.headers, fallback)
        return response.read(), filename


def slack_token(provider: dict[str, object], args: argparse.Namespace) -> str:
    if args.token_env:
        return os.environ.get(args.token_env, "")
    token_env = provider.get("token_env", "")
    return os.environ.get(str(token_env), "") if token_env else ""


def slack_file_url(provider: dict[str, object], args: argparse.Namespace) -> str:
    if args.url:
        return args.url
    token = slack_token(provider, args)
    if not token:
        raise SystemExit("slack-web-api requires a token via --token-env or provider token_env")
    if not args.file_id:
        raise SystemExit("slack-web-api requires --file-id or --url")
    query = urllib.parse.urlencode({"file": args.file_id})
    request = urllib.request.Request(
        f"https://slack.com/api/files.info?{query}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise SystemExit(f"slack files.info failed: {payload.get('error', 'unknown_error')}")
    file_info = payload.get("file", {})
    if not isinstance(file_info, dict):
        raise SystemExit("slack files.info response missing file object")
    url = file_info.get("url_private_download") or file_info.get("url_private")
    if not url:
        raise SystemExit("slack file response missing url_private_download")
    return str(url)


def fetch_direct_url(provider: dict[str, object], args: argparse.Namespace) -> tuple[bytes, str, str]:
    url = args.url or str(provider.get("url", ""))
    if not url and provider.get("url_env"):
        url = os.environ.get(str(provider["url_env"]), "")
    if not url:
        raise SystemExit("direct-url provider requires --url, provider url, or provider url_env")
    data, filename = read_url(url)
    return data, filename, url


def fetch_slack(provider: dict[str, object], args: argparse.Namespace) -> tuple[bytes, str, str]:
    url = slack_file_url(provider, args)
    token = slack_token(provider, args)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    data, filename = read_url(url, headers)
    return data, filename, url


def fetch_command(root: Path, provider: dict[str, object], args: argparse.Namespace, out: Path) -> tuple[bytes | None, str, str]:
    command = provider.get("command", [])
    if isinstance(command, str):
        command = shlex.split(command)
    if not isinstance(command, list) or not command:
        raise SystemExit("command provider requires command list")
    env = dict(os.environ)
    env.update(
        {
            "OPERATOR_FILE_ID": args.file_id,
            "OPERATOR_FILE_URL": args.url,
            "OPERATOR_OUTPUT_PATH": out.as_posix(),
            "OPERATOR_ROOT": root.as_posix(),
        }
    )
    timeout = provider.get("timeout_seconds") if isinstance(provider.get("timeout_seconds"), int) else 300
    try:
        result = subprocess.run([str(part) for part in command], capture_output=True, env=env, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"command provider timed out after {timeout}s")
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace")[:1000]
        raise SystemExit(f"command provider failed with {result.returncode}: {detail}")
    if out.exists() and out.stat().st_size:
        return None, out.name, args.url or args.file_id or "command"
    return result.stdout, out.name, args.url or args.file_id or "command"


def parse_metadata(values: list[str]) -> dict[str, str]:
    parsed = {}
    for item in values:
        key, sep, value = item.partition("=")
        if sep:
            parsed[key.strip()] = value.strip()
    return parsed


def write_download(out: Path, data: bytes | None) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if data is not None:
        tmp = out.with_suffix(out.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--provider", default="", help="Provider key under file_sources.chat.providers.")
    parser.add_argument("--url", default="", help="Source URL or provider-specific private download URL.")
    parser.add_argument("--file-id", default="", help="Provider-specific file identifier.")
    parser.add_argument("--token-env", default="", help="Environment variable containing a provider token.")
    parser.add_argument("--output", default="", help="Output path. Defaults to local-private/chat-downloads/.")
    parser.add_argument("--filename", default="", help="Preferred filename when provider cannot infer one.")
    parser.add_argument("--metadata", action="append", default=[], help="Extra key=value metadata.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    provider_name = args.provider or default_provider(config)
    provider = provider_config(config, provider_name)
    adapter = str(provider.get("type", provider_name))
    fallback_name = args.filename or args.file_id or filename_from_url(args.url or provider_name)
    out = output_path(root, config, args, fallback_name)

    if adapter == "direct-url":
        data, filename, source = fetch_direct_url(provider, args)
        if not args.output:
            out = output_path(root, config, args, args.filename or filename)
    elif adapter == "slack-web-api":
        data, filename, source = fetch_slack(provider, args)
        if not args.output:
            out = output_path(root, config, args, args.filename or filename)
    elif adapter == "command":
        data, filename, source = fetch_command(root, provider, args, out)
    else:
        raise SystemExit(f"unsupported chat file provider type: {adapter}")

    write_download(out, data)
    metadata = {
        "fetched_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provider": provider_name,
        "provider_type": adapter,
        "file_id": args.file_id,
        "source": source,
        "stored_path": relpath(root, out),
        "sha256": sha256(out),
        "bytes": out.stat().st_size,
        "extra": parse_metadata(args.metadata),
    }
    metadata_path = out.with_suffix(out.suffix + ".metadata.json")
    write_json(metadata_path, metadata)
    print(relpath(root, out))
    print(relpath(root, metadata_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
