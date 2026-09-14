#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf-interleave_tool_diy — 奇数页 / 偶数页 PDF 交叉合并、拆分与校验

三个子命令：
  merge   把 odd.pdf（1,3,5...）与 even.pdf（2,4,6...）交叉合并为 1,2,3,4... 的完整 PDF
  split   merge 的逆操作：把一个完整 PDF 拆成 *_odd.pdf 与 *_even.pdf
  verify  用页面位图哈希校验合并结果的页序是否正确（可单独调用）
  info    只看页数 / 页面尺寸 / 文件大小，不做任何写操作

设计要点：
  * 等页数时一一配对；不等页数时默认把多出的尾页原样追加，**绝不丢页**
  * --pad blank 可在短的一侧补空白页，保证后续页面的奇偶配对不串位
  * --drop-odd / --drop-even 处理「双面打印翻面扫描缺页」造成的 ±N 偏移
  * 自动寻找装有 PyMuPDF 的解释器并在子进程中重跑（本机实测：managed 裸解释器无 fitz）
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

PIP_HINT = "pip install pymupdf"
REEXEC_FLAG = "PDF_INTERLEAVE_REEXEC"


# --------------------------------------------------------------------------- #
# 解释器 / 依赖自举
# --------------------------------------------------------------------------- #
def _explicit_python() -> str | None:
    for i, a in enumerate(sys.argv):
        if a == "--python" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith("--python="):
            return a.split("=", 1)[1]
    return None


def _candidate_pythons() -> list[str]:
    cands = []
    if os.environ.get("PDF_INTERLEAVE_PYTHON"):
        cands.append(os.environ["PDF_INTERLEAVE_PYTHON"])
    if _explicit_python():
        cands.append(_explicit_python())
    home = os.path.expanduser("~")
    for pat in (
        os.path.join(home, ".workbuddy", "binaries", "python", "envs", "*", "Scripts", "python.exe"),
        os.path.join(home, ".workbuddy", "binaries", "python", "envs", "*", "bin", "python"),
        os.path.join(home, "miniconda3", "python.exe"),
        os.path.join(home, "anaconda3", "python.exe"),
    ):
        cands.extend(sorted(glob.glob(pat)))
    cands.append(sys.executable)
    out, seen = [], set()
    for c in cands:
        if c and os.path.isfile(c) and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out


def import_fitz():
    try:
        import fitz  # noqa
        return fitz
    except ImportError:
        pass
    if os.environ.get(REEXEC_FLAG) == "1":
        sys.exit(f"[ERROR] 解释器 {sys.executable} 里没有 PyMuPDF(fitz)，请先 {PIP_HINT}")
    for py in _candidate_pythons():
        if os.path.abspath(py) == os.path.abspath(sys.executable):
            continue  # 当前解释器刚刚已确认无 fitz，无需再探
        try:
            probe = subprocess.run([py, "-c", "import fitz"], capture_output=True)
        except OSError:
            continue
        if probe.returncode == 0:
            env = dict(os.environ, **{REEXEC_FLAG: "1"})
            child = subprocess.run([py, os.path.abspath(__file__)] + sys.argv[1:], env=env)
            sys.exit(child.returncode)
    sys.exit(f"[ERROR] 未找到装有 PyMuPDF 的解释器；请先 {PIP_HINT}，或用 --python 指定。")


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def die(msg: str, code: int = 1):
    print(f"[ERROR] {msg}")
    sys.exit(code)


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0


def open_doc(fitz, path: str):
    if not path or not os.path.isfile(path):
        die(f"文件不存在: {path}")
    doc = fitz.open(path)
    if doc.is_encrypted and doc.needs_pass:
        die(f"文件被密码保护，无法读取: {path}")
    if doc.page_count == 0:
        die(f"文件没有页面: {path}")
    return doc


def page_hash(doc, idx: int, dpi: int = 72) -> str:
    """页面位图哈希：像素级比对，能捕捉内容、裁切、旋转的差异。"""
    pm = doc[idx].get_pixmap(dpi=dpi)
    h = hashlib.md5()
    h.update(f"{pm.width}x{pm.height}|{pm.n}".encode())
    h.update(pm.samples)
    return h.hexdigest()


def save_pdf(fitz, out: "fitz.Document", out_path: str):
    d = os.path.dirname(os.path.abspath(out_path))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    out.save(out_path, garbage=4, deflate=True)
    out.close()


# --------------------------------------------------------------------------- #
# merge
# --------------------------------------------------------------------------- #
def cmd_merge(fitz, args) -> dict:
    odd = open_doc(fitz, args.odd)
    even = open_doc(fitz, args.even)

    odd_idx = list(range(args.drop_odd, odd.page_count))
    even_idx = list(range(args.drop_even, even.page_count))
    if not odd_idx and not even_idx:
        die("两侧页面都被 --drop-* 排空了，没有可合并的内容。")

    first_is_odd = args.first == "odd"
    out = fitz.open()
    mapping = []          # (out_page_0based, src, src_page_0based)
    pads = []

    n = max(len(odd_idx), len(even_idx))
    for i in range(n):
        pair = []
        if i < len(odd_idx):
            pair.append(("odd", odd, odd_idx[i]))
        elif args.pad == "blank":
            pair.append(("PAD", even, even_idx[-1] if even_idx else 0))
        if i < len(even_idx):
            pair.append(("even", even, even_idx[i]))
        elif args.pad == "blank":
            pair.append(("PAD", odd, odd_idx[-1] if odd_idx else 0))
        if not first_is_odd:
            pair.reverse()

        for src, doc, pno in pair:
            if src == "PAD":
                out.new_page(width=doc[0].rect.width, height=doc[0].rect.height)
                pads.append(len(out) - 1)
                continue
            out.insert_pdf(doc, from_page=pno, to_page=pno)
            mapping.append((len(out) - 1, src, pno))

    save_pdf(fitz, out, args.output)

    result = {
        "command": "merge",
        "output": os.path.abspath(args.output),
        "output_size": human(os.path.getsize(args.output)),
        "output_pages": len(mapping) + len(pads),
        "odd_pages": odd.page_count,
        "even_pages": even.page_count,
        "odd_used": len(odd_idx),
        "even_used": len(even_idx),
        "first": args.first,
        "padded_blank_pages": len(pads),
    }

    # 尾部对齐提示
    tail_note = None
    if len(odd_idx) != len(even_idx) and args.pad == "none":
        longer = "odd.pdf" if len(odd_idx) > len(even_idx) else "even.pdf"
        extra = abs(len(odd_idx) - len(even_idx))
        tail_note = (f"{longer} 比另一侧多 {extra} 页，已原样追加在文件末尾，未丢页；"
                     f"若需保持奇偶配对不串位请加 --pad blank。")
    if tail_note:
        result["tail_note"] = tail_note

    if args.verify:
        result["verify"] = do_verify(fitz, args.output, args.odd, args.even,
                                     first=args.first, drop_odd=args.drop_odd,
                                     drop_even=args.drop_even, pad=args.pad,
                                     mapping=mapping, pads=pads)
    odd.close()
    even.close()
    return result


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #
def do_verify(fitz, merged_path, odd_path, even_path, first="odd",
              drop_odd=0, drop_even=0, pad="none", mapping=None, pads=None) -> dict:
    merged = open_doc(fitz, merged_path)
    odd = open_doc(fitz, odd_path)
    even = open_doc(fitz, even_path)

    if mapping is None:
        mapping, pads = [], []
        odd_idx = list(range(drop_odd, odd.page_count))
        even_idx = list(range(drop_even, even.page_count))
        n = max(len(odd_idx), len(even_idx))
        pos = 0
        for i in range(n):
            pair = []
            if i < len(odd_idx):
                pair.append(("odd", odd_idx[i]))
            elif pad == "blank":
                pair.append(("PAD", None))
            if i < len(even_idx):
                pair.append(("even", even_idx[i]))
            elif pad == "blank":
                pair.append(("PAD", None))
            if first != "odd":
                pair.reverse()
            for src, pno in pair:
                if src == "PAD":
                    pads.append(pos)
                else:
                    mapping.append((pos, src, pno))
                pos += 1

    src_docs = {"odd": odd, "even": even}
    mismatches = []
    checked = 0
    for out_pos, src, pno in mapping:
        if out_pos >= merged.page_count:
            mismatches.append({"out_page": out_pos + 1, "expected": f"{src}[{pno+1}]",
                               "actual": "missing"})
            continue
        if page_hash(merged, out_pos) != page_hash(src_docs[src], pno):
            mismatches.append({"out_page": out_pos + 1, "expected": f"{src}[{pno+1}]",
                               "actual": "content mismatch"})
        checked += 1

    # 空白填充页应为白纸
    for p in (pads or []):
        if p < merged.page_count and page_hash(merged, p) != page_hash_blank(fitz, merged, p):
            mismatches.append({"out_page": p + 1, "expected": "blank pad", "actual": "not blank"})

    paired = checked + len(pads or [])
    result = {
        "checked_pages": paired,
        "mismatches": len(mismatches),
        "verdict": "ALL MATCH" if not mismatches else "FAILED",
    }
    if mismatches:
        result["detail"] = mismatches[:20]
    if paired != merged.page_count:
        result["note"] = f"合并件共 {merged.page_count} 页，本次比对了 {paired} 页"
    merged.close()
    odd.close()
    even.close()
    return result


def page_hash_blank(fitz, doc, idx) -> str:
    """生成同尺寸纯白页的哈希，用于判定填充页确实是空白。"""
    r = doc[idx].rect
    tmp = fitz.open()
    tmp.new_page(width=r.width, height=r.height)
    h = page_hash(tmp, 0)
    tmp.close()
    return h


# --------------------------------------------------------------------------- #
# split
# --------------------------------------------------------------------------- #
def cmd_split(fitz, args) -> dict:
    src = open_doc(fitz, args.input)
    outdir = args.outdir or os.path.dirname(os.path.abspath(args.input))
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.input))[0]
    p_odd, p_even = args.prefix
    odd_out = os.path.join(outdir, f"{stem}_{p_odd}.pdf")
    even_out = os.path.join(outdir, f"{stem}_{p_even}.pdf")

    odd = fitz.open()
    even = fitz.open()
    for i in range(src.page_count):
        tgt = odd if i % 2 == 0 else even          # 第 1 页(i=0) → odd
        tgt.insert_pdf(src, from_page=i, to_page=i)

    save_pdf(fitz, odd, odd_out)
    save_pdf(fitz, even, even_out)
    src_pages = src.page_count
    src.close()

    result = {
        "command": "split",
        "input": os.path.abspath(args.input),
        "input_pages": src_pages,
        "odd_out": os.path.abspath(odd_out),
        "even_out": os.path.abspath(even_out),
    }
    d = fitz.open(args.input)
    o = fitz.open(odd_out)
    e = fitz.open(even_out)
    result["odd_pages"] = o.page_count
    result["even_pages"] = e.page_count
    if o.page_count + e.page_count != d.page_count:
        die("拆分页数与原件不符，已中止")
    if args.verify:
        result["verify"] = do_verify(fitz, args.input, odd_out, even_out, first="odd")
    o.close()
    e.close()
    d.close()
    return result


# --------------------------------------------------------------------------- #
# info
# --------------------------------------------------------------------------- #
def cmd_info(fitz, args) -> dict:
    out = {"command": "info", "files": []}
    for path in args.paths:
        doc = open_doc(fitz, path)
        sizes = {}
        for i in range(doc.page_count):
            r = doc[i].rect
            key = f"{round(r.width, 1)}x{round(r.height, 1)}"
            sizes[key] = sizes.get(key, 0) + 1
        out["files"].append({
            "path": os.path.abspath(path),
            "pages": doc.page_count,
            "file_size": human(os.path.getsize(path)),
            "page_sizes": sizes,
            "uniform_size": len(sizes) == 1,
        })
        doc.close()
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser():
    # --json / --python 同时挂在主命令和子命令上，两处都能写；
    # 用 SUPPRESS 作默认值，避免子解析器把主解析器已设的值覆盖回 False
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--python", default=argparse.SUPPRESS,
                        help="指定装有 PyMuPDF 的解释器（默认自动探测）")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="以 JSON 输出结果，便于程序解析")

    p = argparse.ArgumentParser(
        prog="interleave_pdf",
        description="奇数页/偶数页 PDF 交叉合并、拆分与页序校验",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[common],
        epilog=(
            "示例:\n"
            "  python interleave_pdf.py merge odd.pdf even.pdf -o merged.pdf\n"
            "  python interleave_pdf.py merge odd.pdf even.pdf -o merged.pdf --verify\n"
            "  python interleave_pdf.py merge even.pdf odd.pdf -o merged.pdf --first even\n"
            "  python interleave_pdf.py merge odd.pdf even.pdf -o merged.pdf --drop-odd 1\n"
            "  python interleave_pdf.py split merged.pdf -o ./out --verify\n"
            "  python interleave_pdf.py verify merged.pdf --odd odd.pdf --even even.pdf\n"
            "  python interleave_pdf.py info odd.pdf even.pdf\n"
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("merge", parents=[common], help="交叉合并 odd/even 两个 PDF")
    m.add_argument("odd", help="奇数页那一路文件（正常情况下含 1,3,5... 页）")
    m.add_argument("even", help="偶数页那一路文件（正常情况下含 2,4,6... 页）")
    m.add_argument("-o", "--output", required=True, help="输出的新 PDF 路径")
    m.add_argument("--first", choices=["odd", "even"], default="odd",
                   help="合并件第 1 页取自哪一路（默认 odd）。"
                        "等价写法：merge A B --first even == merge B A（把 B 那一路放前面）")
    m.add_argument("--drop-odd", type=int, default=0, metavar="N",
                   help="跳过 odd 文件开头 N 页，用于修正 ±N 页偏移")
    m.add_argument("--drop-even", type=int, default=0, metavar="N",
                   help="跳过 even 文件开头 N 页")
    m.add_argument("--pad", choices=["none", "blank"], default="none",
                   help="页数不等时：none=尾页原样追加（默认，不丢页），blank=补空白页保配对")
    m.add_argument("--verify", action="store_true", help="合并后逐页位图比对校验页序")
    m.add_argument("--no-overwrite", action="store_true", help="输出文件已存在时拒绝覆盖")

    s = sub.add_parser("split", parents=[common], help="把完整 PDF 拆成奇数页/偶数页两个文件")
    s.add_argument("input", help="待拆分的完整 PDF")
    s.add_argument("-o", "--outdir", help="输出目录（默认与输入同目录）")
    s.add_argument("--prefix", default="odd,even", metavar="ODD,EVEN",
                   help="两个输出文件的后缀名，逗号分隔（默认 odd,even）")
    s.add_argument("--verify", action="store_true", help="拆分后回拼校验是否与原件一致")

    v = sub.add_parser("verify", parents=[common], help="校验已有合并件的页序")
    v.add_argument("merged", help="待校验的合并件")
    v.add_argument("--odd", required=True, help="奇数页源文件")
    v.add_argument("--even", required=True, help="偶数页源文件")
    v.add_argument("--first", choices=["odd", "even"], default="odd")
    v.add_argument("--drop-odd", type=int, default=0, metavar="N")
    v.add_argument("--drop-even", type=int, default=0, metavar="N")
    v.add_argument("--pad", choices=["none", "blank"], default="none")

    i = sub.add_parser("info", parents=[common], help="查看页数 / 页面尺寸 / 文件大小")
    i.add_argument("paths", nargs="+", help="一个或多个 PDF")
    return p


def main():
    args = build_parser().parse_args()
    as_json = getattr(args, "json", False)   # --json 可写在子命令前后任意位置
    fitz = import_fitz()

    if args.cmd == "merge":
        if args.no_overwrite and os.path.exists(args.output):
            die(f"输出文件已存在（--no-overwrite）: {args.output}")
        if os.path.abspath(args.odd) == os.path.abspath(args.even):
            die("两个输入文件是同一个文件，请检查参数顺序。")
        if os.path.abspath(args.output) in (os.path.abspath(args.odd), os.path.abspath(args.even)):
            die("输出路径与输入文件相同，会覆盖原始数据，请换一个 -o 路径。")
        res = cmd_merge(fitz, args)

    elif args.cmd == "split":
        parts = [x.strip() for x in args.prefix.split(",") if x.strip()]
        if len(parts) != 2:
            die("--prefix 需要两个名字，如 --prefix odd,even")
        args.prefix = (parts[0], parts[1])
        res = cmd_split(fitz, args)

    elif args.cmd == "verify":
        res = do_verify(fitz, args.merged, args.odd, args.even, first=args.first,
                        drop_odd=args.drop_odd, drop_even=args.drop_even, pad=args.pad)

    else:
        res = cmd_info(fitz, args)

    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        for k, v in res.items():
            if isinstance(v, dict):
                print(f"{k}:")
                for kk, vv in v.items():
                    print(f"  {kk}: {vv}")
            elif isinstance(v, list):
                print(f"{k}:")
                for it in v:
                    print(f"  - {it}")
            else:
                print(f"{k}: {v}")
    if res.get("verdict") == "FAILED" or res.get("mismatches"):
        sys.exit(2)
    if isinstance(res.get("verify"), dict) and res["verify"].get("verdict") == "FAILED":
        sys.exit(2)


if __name__ == "__main__":
    main()
