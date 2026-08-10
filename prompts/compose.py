#!/usr/bin/env python3
"""
URace Sales Agent — prompt composer.

Assembles the final system prompt for a given conversation mode by layering:
    master  →  context  →  mode

and returns the tool subset that mode is allowed to use.

Usage:
    python compose.py --mode qualification
    python compose.py --mode faq --context sample_context.json
    python compose.py --list
    python compose.py --check          # sanity checks before shipping a prompt change
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
MASTER = ROOT / "00_master.md"
CONTEXT = ROOT / "01_context_template.md"
MODES_DIR = ROOT / "modes"
TOOLS = ROOT / "tools" / "tools.json"

MODES = ["faq", "qualification", "scheduling", "followup", "escalation"]

# Business facts must never appear in prompt files — they belong in the catalog,
# fetched via tools at runtime. This guards the core architectural rule.
FORBIDDEN_PATTERNS = [
    (r"\$\s?\d", "a hardcoded price"),
    (r"\b(769|719|819|2756|3156|689|395|245)\b", "a hardcoded amount"),
    (r"\b(Summer Camp|URace Academy|Lead & Follow|Arrive & Drive)\b", "a program name"),
    (r"\b\d+\s*(years old|anos)\b", "a hardcoded age"),
]
# Files exempt from the scan: they legitimately discuss the rules themselves.
SCAN_EXEMPT = {"README.md"}


def read(path: Path) -> str:
    if not path.exists():
        sys.exit(f"ERROR: missing file {path}")
    return path.read_text(encoding="utf-8")


def load_tools(mode: str):
    data = json.loads(read(TOOLS))
    out = []
    for tool in data["tools"]:
        if mode in tool.get("modes", []):
            t = {k: v for k, v in tool.items() if k != "modes"}
            out.append(t)
    return out


def fill(template: str, context: dict) -> str:
    """Replace {{ key }} and {{ key | "fallback" }} placeholders."""
    def repl(match):
        body = match.group(1).strip()
        if "|" in body:
            key, fallback = body.split("|", 1)
            key, fallback = key.strip(), fallback.strip().strip('"\'')
        else:
            key, fallback = body, "(not captured)"
        value = context.get(key)
        return str(value) if value not in (None, "") else fallback

    return re.sub(r"\{\{(.*?)\}\}", repl, template)


def compose(mode: str, context: dict | None = None) -> tuple[str, list]:
    if mode not in MODES:
        sys.exit(f"ERROR: unknown mode '{mode}'. Valid: {', '.join(MODES)}")

    context = context or {}
    parts = [
        read(MASTER),
        "\n\n---\n\n",
        fill(read(CONTEXT), context),
        "\n\n---\n\n",
        fill(read(MODES_DIR / f"{mode}.md"), context),
    ]
    return "".join(parts), load_tools(mode)


def check() -> int:
    """Guard the architecture rule: no business data inside prompt files."""
    problems = []
    files = [MASTER, CONTEXT] + sorted(MODES_DIR.glob("*.md"))

    for path in files:
        if path.name in SCAN_EXEMPT:
            continue
        text = read(path)
        for pattern, label in FORBIDDEN_PATTERNS:
            for m in re.finditer(pattern, text, flags=re.IGNORECASE):
                line = text[: m.start()].count("\n") + 1
                problems.append(f"  {path.name}:{line}  {label} → {m.group(0)!r}")

    for mode in MODES:
        if not (MODES_DIR / f"{mode}.md").exists():
            problems.append(f"  missing mode file: {mode}.md")
        if not load_tools(mode):
            problems.append(f"  mode '{mode}' has no tools assigned")

    if problems:
        print("FAILED — business data or structure problems found:\n")
        print("\n".join(problems))
        print(
            "\nPrompts must not contain prices, program names, or ages.\n"
            "Those live in the catalog and reach the agent through tool calls."
        )
        return 1

    print("OK — no business data in prompts; all modes present with tools.")
    for mode in MODES:
        text, tools = compose(mode)
        print(f"  {mode:14} ~{len(text)//4:>5} tokens   {len(tools)} tools")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Compose the URace agent system prompt.")
    ap.add_argument("--mode", choices=MODES)
    ap.add_argument("--context", type=Path, help="JSON file with context values.")
    ap.add_argument("--out", type=Path, help="Write the prompt to a file.")
    ap.add_argument("--tools", action="store_true", help="Print the tool subset instead.")
    ap.add_argument("--list", action="store_true", help="List modes and their tools.")
    ap.add_argument("--check", action="store_true", help="Run pre-ship sanity checks.")
    args = ap.parse_args()

    if args.check:
        sys.exit(check())

    if args.list:
        for mode in MODES:
            names = [t["name"] for t in load_tools(mode)]
            print(f"{mode:14} {', '.join(names)}")
        return

    if not args.mode:
        ap.error("--mode is required (or use --list / --check)")

    ctx = json.loads(read(args.context)) if args.context else {}
    prompt, tools = compose(args.mode, ctx)

    if args.tools:
        print(json.dumps(tools, indent=2, ensure_ascii=False))
        return

    if args.out:
        args.out.write_text(prompt, encoding="utf-8")
        print(f"Wrote {args.out}  (~{len(prompt)//4} tokens, {len(tools)} tools)")
    else:
        print(prompt)


if __name__ == "__main__":
    main()
