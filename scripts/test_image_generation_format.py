#!/usr/bin/env python3
"""Quick check for image-generation API payload format.

Usage:
  python scripts/test_image_generation_format.py --prompt "draw a cat"
  python scripts/test_image_generation_format.py --load-raw data/raw_response_123.json
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.image_service import _extract_image_payload


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def normalize_endpoint(base: str) -> str:
    b = base.strip()
    if b.endswith("/chat/completions"):
        return b
    if b.endswith("/v1"):
        return f"{b}/chat/completions"
    if b.endswith("/v1/"):
        return f"{b}chat/completions"
    if b.endswith("/"):
        return f"{b}chat/completions"
    return f"{b}/chat/completions"


def _mime_to_ext(mime_type: str | None) -> str:
    """Convert MIME type to file extension."""
    if not mime_type:
        return ".png"
    mime = mime_type.lower()
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
        "image/svg+xml": ".svg",
    }
    return mapping.get(mime, ".png")


def _save_base64_image(image_b64: str, mime_type: str | None, output_dir: Path) -> Path:
    """Save base64 encoded image to file and return the file path."""
    ext = _mime_to_ext(mime_type)
    timestamp = int(time.time() * 1000)
    filename = f"generated_{timestamp}{ext}"
    output_path = output_dir / filename

    # Decode base64 and save
    image_data = base64.b64decode(image_b64)
    output_path.write_bytes(image_data)

    return output_path


def _save_raw_response(
    raw_data: dict[str, Any],
    output_dir: Path,
    *,
    prefix: str = "raw_response",
) -> Path:
    """Save raw API response to JSON file."""
    timestamp = int(time.time() * 1000)
    filename = f"{prefix}_{timestamp}.json"
    output_path = output_dir / filename
    output_path.write_text(
        json.dumps(raw_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


def _print_raw_preview(raw_text: str, max_chars: int) -> None:
    if max_chars <= 0 or len(raw_text) <= max_chars:
        print(raw_text)
        return
    print(raw_text[:max_chars])
    print(
        f"\n... (truncated, total {len(raw_text)} chars; "
        f"use --raw-max-chars 0 to print full response)"
    )


def _normalize_for_print(payload: dict) -> dict:
    out = dict(payload)
    image_url = out.get("image_url")
    if isinstance(image_url, str) and image_url.startswith("data:image/"):
        prefix = image_url[:80]
        out["image_url"] = f"{prefix}... (len={len(image_url)})"
    image_b64 = out.get("image_b64")
    if isinstance(image_b64, str):
        out["image_b64"] = f"{image_b64[:80]}... (len={len(image_b64)})"
    return out


def _image_path_to_data_url(path: Path) -> str:
    mime_type, _encoding = mimetypes.guess_type(path.name)
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/png"
    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_assistant_content(parsed: dict[str, Any]) -> str | list[dict[str, Any]] | None:
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        blocks: list[dict[str, Any]] = []
        for item in content:
            if isinstance(item, dict):
                blocks.append(item)
        return blocks if blocks else None
    return None


def _request_chat_completion(
    *,
    endpoint: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
) -> str:
    payload = {
        "model": model,
        "stream": False,
        "messages": messages,
    }
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    req = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8")


def _print_and_save_round(
    *,
    round_label: str,
    raw_text: str,
    output_dir: Path,
    raw_max_chars: int,
) -> tuple[dict[str, Any], dict[str, Any], Path | None, Path]:
    print(f"=== {round_label} RAW RESPONSE ===")
    _print_raw_preview(raw_text, raw_max_chars)

    parsed = json.loads(raw_text)
    saved_raw_path = _save_raw_response(
        parsed,
        output_dir,
        prefix=f"raw_response_{round_label.lower()}",
    )
    print(f"\n=== {round_label} RAW RESPONSE SAVED ===")
    print(f"Path: {saved_raw_path}")

    normalized = _extract_image_payload(parsed)
    print(f"\n=== {round_label} NORMALIZED ===")
    print(json.dumps(_normalize_for_print(normalized), ensure_ascii=False, indent=2))

    saved_image_path: Path | None = None
    image_b64 = normalized.get("image_b64")
    if image_b64:
        saved_image_path = _save_base64_image(
            image_b64,
            normalized.get("mime_type"),
            output_dir,
        )
        print(f"\n=== {round_label} IMAGE SAVED ===")
        print(f"Path: {saved_image_path}")
        print(f"MIME type: {normalized.get('mime_type') or 'image/png'}")

    return parsed, normalized, saved_image_path, saved_raw_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", default="画只猫")
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-base", default=None)
    parser.add_argument(
        "--load-raw",
        type=Path,
        default=None,
        help="Load raw response from JSON file instead of calling API",
    )
    parser.add_argument(
        "--raw-max-chars",
        type=int,
        default=3000,
        help="Max chars to print for raw JSON (0 = print all)",
    )
    parser.add_argument(
        "--multi-round",
        action="store_true",
        help="Run a second round using round-1 generated image as reference.",
    )
    parser.add_argument(
        "--second-prompt",
        default=(
            "参考上一张图保持同样风格与角色身份，把猫修正为四条腿，"
            "解剖结构自然，保留侦探风格与电影感光影。"
        ),
        help="Second-round prompt used when --multi-round is enabled.",
    )
    parser.add_argument(
        "--reference-mode",
        choices=["image_url", "assistant_content", "text_only"],
        default="image_url",
        help="How round-2 references round-1 output.",
    )
    parser.add_argument(
        "--reference-image",
        action="append",
        type=Path,
        default=[],
        help=(
            "Local image file path used as visual reference in round-1 request. "
            "Can be specified multiple times."
        ),
    )
    args = parser.parse_args()

    output_dir = REPO_ROOT / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load from file if specified
    if args.load_raw:
        if args.multi_round:
            print("--multi-round cannot be used together with --load-raw.")
            return 1
        if args.reference_image:
            print("--reference-image cannot be used together with --load-raw.")
            return 1
        if not args.load_raw.exists():
            print(f"File not found: {args.load_raw}")
            return 1
        raw_text = args.load_raw.read_text(encoding="utf-8")
        print(f"=== LOADED FROM {args.load_raw} ===")
        _print_raw_preview(raw_text, args.raw_max_chars)
    else:
        # Call API
        # Always load repo-root .env, so running from scripts/ or elsewhere still works.
        load_env_file(REPO_ROOT / ".env")

        model = (
            args.model
            or os.getenv("IMAGE_GEN_MODEL")
            or "gemini-2.5-flash-image-preview"
        )
        api_key = (os.getenv("IMAGE_GEN_API_KEY") or "").strip()
        api_base = (
            args.api_base
            or os.getenv("IMAGE_GEN_API_BASE")
            or "https://api.whatai.cc/v1/chat/completions"
        )
        endpoint = normalize_endpoint(api_base)

        if not api_key:
            print("IMAGE_GEN_API_KEY is empty. Set it in .env or env vars.")
            return 1
        print("=== REQUEST CONFIG ===")
        print(f"model={model}")
        print(f"endpoint={endpoint}")
        if args.reference_image:
            print("reference_images=" + ", ".join(str(p) for p in args.reference_image))

        missing_reference = [p for p in args.reference_image if not p.exists()]
        if missing_reference:
            print("Missing reference images:")
            for path in missing_reference:
                print(f"- {path}")
            return 1

        round1_messages: list[dict[str, Any]]
        if args.reference_image:
            content: list[dict[str, Any]] = [{"type": "text", "text": args.prompt}]
            for img_path in args.reference_image:
                data_url = _image_path_to_data_url(img_path)
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    }
                )
            round1_messages = [{"role": "user", "content": content}]
        else:
            round1_messages = [{"role": "user", "content": args.prompt}]

        try:
            raw_text = _request_chat_completion(
                endpoint=endpoint,
                api_key=api_key,
                model=model,
                messages=round1_messages,
            )
        except HTTPError as exc:
            print(f"HTTPError: {exc.code}")
            print(exc.read().decode("utf-8", errors="replace"))
            return 2
        except URLError as exc:
            print(f"URLError: {exc.reason}")
            return 3
        try:
            parsed, normalized, _saved_image, saved_raw1 = _print_and_save_round(
                round_label="ROUND1",
                raw_text=raw_text,
                output_dir=output_dir,
                raw_max_chars=args.raw_max_chars,
            )
            print(
                f"\nYou can reload with: --load-raw "
                f"{saved_raw1.name}"
            )
        except Exception as exc:
            print(f"Failed to process round-1 response: {exc}")
            return 5

        if args.multi_round:
            print("\n=== ROUND2 CONFIG ===")
            print(f"reference_mode={args.reference_mode}")
            print(f"second_prompt={args.second_prompt}")

            round2_messages: list[dict[str, Any]]
            if args.reference_mode == "image_url":
                ref_url = normalized.get("image_url")
                if not isinstance(ref_url, str) or not ref_url.strip():
                    print("ROUND1 has no usable image_url for reference.")
                    return 6
                round2_messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": args.second_prompt},
                            {"type": "image_url", "image_url": {"url": ref_url}},
                        ],
                    }
                ]
            elif args.reference_mode == "assistant_content":
                assistant_content = _extract_assistant_content(parsed)
                if assistant_content is None:
                    print("ROUND1 has no assistant content for reference.")
                    return 6
                round2_messages = [
                    {"role": "user", "content": args.prompt},
                    {"role": "assistant", "content": assistant_content},
                    {"role": "user", "content": args.second_prompt},
                ]
            else:
                round2_messages = [
                    {
                        "role": "user",
                        "content": (
                            f"上一次图片提示词：{args.prompt}\n\n"
                            f"新的要求：{args.second_prompt}"
                        ),
                    }
                ]

            try:
                raw_text_round2 = _request_chat_completion(
                    endpoint=endpoint,
                    api_key=api_key,
                    model=model,
                    messages=round2_messages,
                )
            except HTTPError as exc:
                print(f"ROUND2 HTTPError: {exc.code}")
                print(exc.read().decode("utf-8", errors="replace"))
                return 2
            except URLError as exc:
                print(f"ROUND2 URLError: {exc.reason}")
                return 3

            try:
                _parsed2, _normalized2, _saved2, _saved_raw2 = _print_and_save_round(
                    round_label="ROUND2",
                    raw_text=raw_text_round2,
                    output_dir=output_dir,
                    raw_max_chars=args.raw_max_chars,
                )
            except Exception as exc:
                print(f"Failed to process round-2 response: {exc}")
                return 5

            print("\n=== MULTI-ROUND SUMMARY ===")
            print("Round1 and Round2 completed.")
            if _saved2:
                print(f"Round2 image: {_saved2}")

        return 0

    try:
        parsed = json.loads(raw_text)
    except Exception:
        print("Response is not valid JSON.")
        return 4

    try:
        normalized = _extract_image_payload(parsed)
    except Exception as exc:
        print(f"Failed to extract image payload: {exc}")
        return 5

    print("\n=== NORMALIZED ===")
    print(json.dumps(_normalize_for_print(normalized), ensure_ascii=False, indent=2))

    # Save base64 image if present
    image_b64 = normalized.get("image_b64")
    if image_b64:
        mime_type = normalized.get("mime_type")
        try:
            saved_path = _save_base64_image(image_b64, mime_type, output_dir)
            print("\n=== IMAGE SAVED ===")
            print(f"Path: {saved_path}")
            print(f"MIME type: {mime_type or 'image/png'}")
        except Exception as exc:
            print("\n=== ERROR SAVING IMAGE ===")
            print(f"Failed to save image: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
