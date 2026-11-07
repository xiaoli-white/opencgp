import re
import subprocess
from pathlib import Path

DICT = Path("src/i18n/dict.ts")


def tsc_dup_lines() -> list[int]:
    out = subprocess.run(
        ["npx", "tsc", "--noEmit"], capture_output=True, text=True, cwd="."
    ).stdout + subprocess.run(
        ["npx", "tsc", "--noEmit"], capture_output=True, text=True, cwd="."
    ).stderr
    lines = set()
    for m in re.finditer(r"src/i18n/dict\.ts\((\d+),\d+\): error TS1117", out):
        lines.add(int(m.group(1)))
    return sorted(lines)


def enclosing_block(lines: list[str], idx: int) -> int:
    """Index of the line that opens the object containing line idx (0-based)."""
    indent = len(lines[idx]) - len(lines[idx].lstrip())
    for i in range(idx - 1, -1, -1):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("//"):
            continue
        cur = len(lines[i]) - len(lines[i].lstrip())
        if cur < indent and re.match(r"^[A-Za-z_][A-Za-z0-9_]*:\s*\{", stripped):
            return i
    return -1


def fix_once() -> int:
    lines = DICT.read_text(encoding="utf-8").split("\n")
    removed = 0
    dups = tsc_dup_lines()
    if not dups:
        return 0
    drop: set[int] = set()
    for line_no in dups:
        idx = line_no - 1
        if idx in drop or idx >= len(lines):
            continue
        text = lines[idx].strip()
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):", text)
        if not m:
            continue
        key = m.group(1)
        block = enclosing_block(lines, idx)
        if block < 0:
            continue
        # find an earlier identical key inside the same block
        for j in range(block + 1, idx):
            if j in drop:
                continue
            if re.match(r"^\s*" + re.escape(key) + r":", lines[j]):
                drop.add(idx)
                removed += 1
                break
    if drop:
        kept = [l for i, l in enumerate(lines) if i not in drop]
        DICT.write_text("\n".join(kept), encoding="utf-8")
    return removed


total = 0
for round_no in range(1, 6):
    n = fix_once()
    total += n
    print(f"round {round_no}: removed {n}")
    if n == 0:
        break
print("total removed:", total)
