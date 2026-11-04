"""Turn assistant output into renderable segments.

QML's ``Text.MarkdownText`` renders prose well but has no syntax
highlighting, so messages are split into prose, fenced code blocks (rendered
with a tiny built-in highlighter) and ``<think>`` reasoning blocks emitted by
SmolLM3. Works on partial text while a response is still streaming.
"""

from __future__ import annotations

import html
import re

_FENCE = re.compile(r"^```[ \t]*([\w+#.-]*)[^\n]*\n", re.M)
_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"

DARK_SYNTAX = {
    "keyword": "#c792ea",
    "string": "#c3e88d",
    "comment": "#6b7280",
    "number": "#f78c6c",
    "builtin": "#82aaff",
    "text": "#e5e7eb",
}
LIGHT_SYNTAX = {
    "keyword": "#8b3fd9",
    "string": "#2f7d32",
    "comment": "#8a8f98",
    "number": "#c2410c",
    "builtin": "#1d5fd1",
    "text": "#1f2328",
}

_KEYWORDS = {
    "python": "and as assert async await break class continue def del elif else except finally for "
    "from global if import in is lambda nonlocal not or pass raise return try while with yield "
    "None True False self match case",
    "js": "async await break case catch class const continue debugger default delete do else export "
    "extends finally for from function if import in instanceof let new of return static super "
    "switch this throw try typeof var void while yield null undefined true false interface type "
    "enum implements public private protected readonly",
    "c": "auto break case char const continue default do double else enum extern float for goto if "
    "inline int long register return short signed sizeof static struct switch typedef union "
    "unsigned void volatile while bool true false class public private protected virtual template "
    "typename namespace using new delete nullptr this fn let mut pub impl trait use mod match "
    "func var import package struct interface go defer chan map range self Self guard",
    "shell": "if then else elif fi for while do done case esac function in export local return "
    "echo cd sudo",
    "sql": "select from where insert into values update set delete create table drop alter join "
    "left right inner outer on group by order having limit as and or not null is in like "
    "primary key foreign references distinct union all",
}
_LANG_ALIASES = {
    "py": "python", "python": "python", "python3": "python",
    "js": "js", "javascript": "js", "ts": "js", "typescript": "js", "jsx": "js", "tsx": "js",
    "json": "js", "java": "c", "kotlin": "c", "c": "c", "cpp": "c", "c++": "c", "cc": "c",
    "h": "c", "cs": "c", "csharp": "c", "rust": "c", "rs": "c", "go": "c", "swift": "c",
    "bash": "shell", "sh": "shell", "zsh": "shell", "shell": "shell", "console": "shell",
    "sql": "sql",
}
_HASH_COMMENT = {"python", "shell"}


def _tokenizer(lang: str) -> re.Pattern[str]:
    comment = r"#[^\n]*" if lang in _HASH_COMMENT else r"--[^\n]*" if lang == "sql" else r"//[^\n]*|/\*[\s\S]*?\*/"
    return re.compile(
        rf"(?P<comment>{comment})"
        r"|(?P<string>\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`)"
        r"|(?P<number>\b\d+(?:\.\d+)?(?:e[+-]?\d+)?\b|\b0x[0-9a-f]+\b)"
        r"|(?P<word>\b[A-Za-z_][A-Za-z0-9_]*\b)",
        re.I,
    )


def highlight(code: str, lang: str, palette: dict[str, str]) -> str:
    """Return HTML for ``code`` with spans coloured from ``palette``."""
    family = _LANG_ALIASES.get(lang.lower(), "")
    if not family:
        return html.escape(code)
    keywords = set(_KEYWORDS[family].split())
    if family == "sql":
        keywords |= {k.upper() for k in keywords}
    out: list[str] = []
    pos = 0
    for m in _tokenizer(family).finditer(code):
        out.append(html.escape(code[pos : m.start()]))
        kind = m.lastgroup
        token = m.group()
        color = None
        if kind == "word":
            if token in keywords:
                color = palette["keyword"]
            elif m.end() < len(code) and code[m.end()] == "(":
                color = palette["builtin"]
        else:
            color = palette[kind]
        escaped = html.escape(token)
        out.append(f'<span style="color:{color}">{escaped}</span>' if color else escaped)
        pos = m.end()
    out.append(html.escape(code[pos:]))
    return "".join(out)


def _split_code(text: str, palette: dict[str, str]) -> list[dict]:
    segments: list[dict] = []
    pos = 0
    while True:
        m = _FENCE.search(text, pos)
        if not m:
            break
        before = text[pos : m.start()]
        if before.strip():
            segments.append({"kind": "text", "text": before.strip("\n"), "lang": "", "html": ""})
        lang = m.group(1)
        close = re.compile(r"^[ \t]*```[ \t]*$", re.M).search(text, m.end())
        code_end = close.start() if close else len(text)
        code = text[m.end() : code_end].rstrip("\n")
        segments.append({
            "kind": "code",
            "text": code,
            "lang": lang,
            "html": highlight(code, lang, palette),
            "open": close is None,
        })
        pos = close.end() if close else len(text)
    tail = text[pos:]
    if tail.strip():
        segments.append({"kind": "text", "text": tail.strip("\n"), "lang": "", "html": ""})
    return segments


def segment_message(text: str, palette: dict[str, str] | None = None) -> list[dict]:
    """Split a (possibly incomplete) message into display segments."""
    palette = palette or DARK_SYNTAX
    segments: list[dict] = []
    rest = text
    start = rest.find(_THINK_OPEN)
    if start != -1 and not rest[:start].strip():
        end = rest.find(_THINK_CLOSE, start)
        thought = rest[start + len(_THINK_OPEN) : end if end != -1 else len(rest)].strip()
        if thought or end == -1:
            segments.append({
                "kind": "think", "text": thought, "lang": "", "html": "", "open": end == -1,
            })
        rest = rest[end + len(_THINK_CLOSE) :] if end != -1 else ""
    segments.extend(_split_code(rest, palette))
    for seg in segments:
        seg.setdefault("open", False)
    return segments


def strip_reasoning(text: str) -> str:
    """Remove ``<think>`` blocks before sending history back to the model."""
    return re.sub(r"<think>[\s\S]*?(</think>|$)", "", text).strip()
