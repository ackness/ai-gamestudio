#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "true")
import litellm

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INIT_PROMPT = (
    "玩家开始了一场新游戏。请根据世界观文档生成一段沉浸式的开场叙事。"
    "在叙事末尾包含一个 json:character_sheet 代码块用于角色创建，"
    "其中 editable_fields 需包含 'name'。"
    "同时包含一个 json:scene_update 代码块来建立起始场景。"
)

DEFAULT_USER_PROMPT = (
    "请进行一次 RPG 能力测试：\n"
    "1) 给出 180~300 字沉浸式开场叙事；\n"
    "2) 在末尾输出一个 ```json:choices``` 代码块（包含 prompt/type/options 字段，至少 3 个选项）；\n"
    "3) 语气保持 DM（游戏主持人）风格，不要解释规则。"
)

PRE_RESPONSE_INSTRUCTIONS = (
    "Respond in character as the DM. You may include structured data blocks "
    "in your response using fenced code blocks with the format ```json:<type>```.\n\n"
    "You may output structured data as ```json:<type>``` blocks at the end "
    "of your narrative text when game state changes occur."
)


@dataclass
class ProjectConfig:
    id: str
    name: str
    world_doc: str
    init_prompt: str | None
    llm_model: str | None
    llm_api_key: str | None
    llm_api_base: str | None
    updated_at: str | None


def ensure_repo_root_on_path() -> None:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="读取 .env（LLM_*）并通过 LiteLLM 执行一次 RPG 快速能力测试。"
    )
    parser.add_argument("--model", help="覆盖模型名，例如 openai/gpt-4o-mini")
    parser.add_argument("--api-key", help="覆盖 API Key（优先级最高）")
    parser.add_argument("--api-base", help="覆盖 API Base（例如 http://localhost:11434）")
    parser.add_argument(
        "--user",
        default=DEFAULT_USER_PROMPT,
        help="测试用的用户输入（默认会要求生成 RPG 开场 + choices 块）",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="采样温度，默认 0.7",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=800,
        help="最大输出 token，默认 800",
    )
    parser.add_argument("--project-id", help="从数据库按 project.id 读取真实提示词")
    parser.add_argument("--project-name", help="从数据库按 project.name 读取真实提示词")
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="不从数据库读取 project 提示词，直接用默认系统提示词",
    )
    parser.add_argument(
        "--system-file",
        type=Path,
        help="从文件读取系统提示词（优先级高于数据库）",
    )
    parser.add_argument(
        "--system-text",
        help="直接指定系统提示词文本（优先级最高）",
    )
    parser.add_argument(
        "--show-system-prompt",
        action="store_true",
        help="打印最终系统提示词全文",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只展示配置与组装后的消息，不实际调用模型",
    )
    return parser.parse_args()


def resolve_sqlite_path(database_url: str) -> Path | None:
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if database_url.startswith(prefix):
            raw = database_url.removeprefix(prefix).split("?", 1)[0]
            if raw == ":memory:":
                return None
            path = Path(raw)
            if not path.is_absolute():
                path = REPO_ROOT / path
            return path
    return None


def load_project_config(
    database_url: str,
    project_id: str | None,
    project_name: str | None,
) -> ProjectConfig | None:
    db_path = resolve_sqlite_path(database_url)
    if not db_path or not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        base_sql = (
            "SELECT id, name, world_doc, init_prompt, llm_model, llm_api_key, "
            "llm_api_base, updated_at FROM project"
        )
        params: tuple[Any, ...] = ()
        if project_id:
            sql = f"{base_sql} WHERE id = ? LIMIT 1"
            params = (project_id,)
        elif project_name:
            sql = f"{base_sql} WHERE name = ? ORDER BY updated_at DESC LIMIT 1"
            params = (project_name,)
        else:
            sql = f"{base_sql} ORDER BY updated_at DESC LIMIT 1"

        row = conn.execute(sql, params).fetchone()
        if not row:
            return None

        return ProjectConfig(
            id=row["id"],
            name=row["name"],
            world_doc=row["world_doc"] or "",
            init_prompt=row["init_prompt"],
            llm_model=row["llm_model"],
            llm_api_key=row["llm_api_key"],
            llm_api_base=row["llm_api_base"],
            updated_at=row["updated_at"],
        )
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def build_system_prompt(
    *,
    project: ProjectConfig | None,
    manual_prompt: str | None,
) -> tuple[str, str]:
    if manual_prompt:
        return manual_prompt.strip(), "manual"

    if project:
        if project.world_doc:
            dm_system = (
                "You are the Dungeon Master (DM) for a role-playing game.\n\n"
                f"## World Document\n\n{project.world_doc.strip()}"
            )
        else:
            dm_system = (
                "You are the Dungeon Master (DM) for a role-playing game. "
                "No world document has been defined yet. Help the player explore."
            )

        init_prompt = (project.init_prompt or DEFAULT_INIT_PROMPT).strip()
        final_prompt = f"{dm_system}\n\n## Opening Instruction\n\n{init_prompt}"
        return final_prompt, f"project:{project.id}"

    fallback = (
        "You are the Dungeon Master (DM) for a role-playing game. "
        "No world document has been defined yet. Help the player explore.\n\n"
        f"## Opening Instruction\n\n{DEFAULT_INIT_PROMPT}"
    )
    return fallback, "default"


def build_messages(system_prompt: str, user_prompt: str) -> list[dict[str, str]]:
    ensure_repo_root_on_path()
    from backend.app.core.prompt_builder import PromptBuilder

    builder = PromptBuilder()
    builder.inject("system", 0, system_prompt)
    builder.inject("chat-history", 0, f"user: {user_prompt.strip()}")
    builder.inject("pre-response", 0, PRE_RESPONSE_INSTRUCTIONS)
    return builder.build()


def _extract_json_choices(response_text: str) -> dict[str, Any] | None:
    pattern = re.compile(r"```json:choices\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)
    match = pattern.search(response_text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def evaluate_rpg_capability(response_text: str) -> list[tuple[str, bool, str]]:
    no_code = re.sub(r"```.*?```", "", response_text, flags=re.DOTALL).strip()
    narrative_len = len(no_code)
    choices_payload = _extract_json_choices(response_text)
    options_count = 0
    if choices_payload and isinstance(choices_payload.get("options"), list):
        options_count = len(choices_payload["options"])

    has_numbered_options = bool(
        re.search(r"(^|\n)\s*(?:1[.)]|2[.)]|3[.)]|[-*])\s+\S+", response_text)
    )

    checks: list[tuple[str, bool, str]] = [
        ("叙事长度 >= 120 字", narrative_len >= 120, f"当前长度: {narrative_len}"),
        (
            "包含结构化 choices 块",
            choices_payload is not None,
            "检测到 `json:choices`" if choices_payload else "未检测到可解析的 `json:choices`",
        ),
        (
            "可行动选项 >= 3",
            options_count >= 3 or has_numbered_options,
            f"choices options 数量: {options_count}",
        ),
    ]
    return checks


async def run_test(args: argparse.Namespace) -> int:
    ensure_repo_root_on_path()
    from backend.app.core.config import Settings

    settings = Settings(_env_file=REPO_ROOT / ".env")

    manual_prompt = args.system_text
    if args.system_file:
        manual_prompt = args.system_file.read_text(encoding="utf-8")

    project = None
    if not args.no_db and not manual_prompt:
        project = load_project_config(
            database_url=settings.DATABASE_URL,
            project_id=args.project_id,
            project_name=args.project_name,
        )

    system_prompt, prompt_source = build_system_prompt(
        project=project,
        manual_prompt=manual_prompt,
    )

    model = args.model or (project.llm_model if project else None) or settings.LLM_MODEL
    api_key = args.api_key or (project.llm_api_key if project else None) or settings.LLM_API_KEY
    api_base = args.api_base or (project.llm_api_base if project else None) or settings.LLM_API_BASE

    print("=== LiteLLM RPG Quick Test ===")
    print(f"model         : {model}")
    print(f"api_base      : {api_base or '(provider default)'}")
    print(f"api_key       : {'set' if api_key else 'not set'}")
    print(f"prompt_source : {prompt_source}")
    if project:
        print(f"project       : {project.name} ({project.id})")
    print()

    if args.show_system_prompt:
        print("----- system prompt begin -----")
        print(system_prompt)
        print("----- system prompt end -----")
        print()

    messages = build_messages(system_prompt, args.user)

    if args.dry_run:
        print("dry_run       : true")
        print(f"messages      : {len(messages)} 条")
        for idx, msg in enumerate(messages, start=1):
            print(f"[message {idx}] role={msg['role']} chars={len(msg['content'])}")
        return 0

    call_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    }
    if api_key:
        call_kwargs["api_key"] = api_key
    if api_base:
        call_kwargs["api_base"] = api_base

    try:
        response = await litellm.acompletion(**call_kwargs)
    except Exception as exc:
        print(f"[ERROR] LiteLLM 调用失败: {type(exc).__name__}: {exc}")
        return 2

    content = response.choices[0].message.content or ""
    print("----- model output begin -----")
    print(content)
    print("----- model output end -----")
    print()

    checks = evaluate_rpg_capability(content)
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print("=== 快速判定 ===")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name} ({detail})")

    if passed == total:
        print("\n结论: 该模型在当前配置下可以用于基础 RPG 回合测试。")
        return 0

    print("\n结论: 该模型输出仍需调优（提示词或模型参数）后再用于 RPG。")
    return 1


def main() -> int:
    args = parse_args()
    return asyncio.run(run_test(args))


if __name__ == "__main__":
    raise SystemExit(main())
