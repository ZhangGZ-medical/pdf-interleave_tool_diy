#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
footer_pageno.py — 把扫描件每页的「页脚印刷页码」裁出来拼成对照图，供人工一眼判读页序。

为什么需要它：
    奇偶页合并翻车几乎都发生在「两侧其实不是同一文档的奇偶页」——比如某一侧整体倒序、
    或中间夹了重复页/空白页。此时 `info` 的页数一样、`merge --verify` 的 ALL MATCH
    都不能说明问题（它们只证明「输出页与它声称的来源页一致」）。
    唯一可靠的判据是**纸上印的页码**。本脚本不做 OCR，只把页脚区域自动裁切、放大、
    按页编号排成一张对照图，由人（或视觉模型）扫一眼就能读出真实页序。

用法：
    python footer_pageno.py odd.pdf even.pdf
    python footer_pageno.py odd.pdf --zoom 6 --y0 0.84 --y1 0.98 --out ./_footers
    python footer_pageno.py odd.pdf --rows 4 --json

判读要点：
    * 页码**递增**的一侧是正面扫描；页码**递减**的一侧是**反面（背面）扫描** ——
      一叠纸整摞翻面后，原来最底下那张变成最上面，页序物理上必然倒置。
      该侧要在 merge 时加 --reverse-odd / --reverse-even
    * 同一页码出现两次 → 重复扫描页（原稿本身重号，或操作员重复扫了一张）
    * 某页 NONE → 该页没印页码（常见于附件首页/空白背面），或多半页码不在 --y0/--y1 区间内
    * 两侧页码不互补（有重号、有断号）→ 不要用 --first / --drop-* 硬凑，
      按印刷页码写自定义页序重建（见 SKILL.md「两侧不是干净的奇偶拆分」一节）

依赖：PyMuPDF(fitz) + numpy + Pillow；缺哪个都会给出明确的安装提示。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HINT = "pip install pymupdf numpy pillow"
REEXEC_FLAG = "PDF_INTERLEAVE_REEXEC"
LABEL_H = 58


def _explicit(arg_name: str):
    for i, a in enumerate(sys.argv):
        if a == arg_name and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(arg_name + "="):
            return a.split("=", 1)[1]
    return None


def _candidate_pythons() -> list[str]:
    cands = []
    env = os.environ.get("PDF_INTERLEAVE_PYTHON")
    if env:
        cands.append(env)
    if _explicit("--python"):
        cands.append(_explicit("--python"))
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


def import_deps():
    have_fitz = have_np = have_pil = False
    try:
        import fitz  # noqa
        have_fitz = True
    except ImportError:
        pass
    try:
        import numpy  # noqa
        have_np = True
    except ImportError:
        pass
    try:
        from PIL import Image  # noqa
        have_pil = True
    except ImportError:
        pass
    if have_fitz and have_np and have_pil:
        import fitz
        import numpy
        from PIL import Image, ImageDraw, ImageFont
        return fitz, numpy, Image, ImageDraw, ImageFont
    if os.environ.get(REEXEC_FLAG) == "1":
        sys.exit(f"[ERROR] 解释器 {sys.executable} 缺依赖（fitz/numpy/Pillow），请先 {HINT}")
    for py in _candidate_pythons():
        if os.path.abspath(py) == os.path.abspath(sys.executable):
            continue
        try:
            probe = subprocess.run([py, "-c", "import fitz, numpy, PIL"], capture_output=True)
        except OSError:
            continue
        if probe.returncode == 0:
            env = dict(os.environ, **{REEXEC_FLAG: "1"})
            sys.exit(subprocess.run([py, os.path.abspath(__file__)] + sys.argv[1:], env=env).returncode)
    sys.exit(f"[ERROR] 未找到装有 fitz+numpy+pillow 的解释器；请先 {HINT}，或用 --python 指定。")


def load_font(ImageFont):
    for p in (r"C:\Windows\Fonts\arialbd.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, 34)
            except Exception:
                pass
    return ImageFont.load_default()


def footer_tile(fitz, np, Image, doc, idx, zoom, y0, y1, min_ink=30):
    """渲染一页的页脚区域，自动裁到墨迹边界，返回等高的灰度小图（找不到墨迹则 None）。"""
    pix = doc[idx].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
    w, h = img.size
    band = np.array(img.crop((0, int(h * y0), w, int(h * y1))))
    ink = band < 150
    # 去掉通栏横线 / 通高竖线（表格框线），只留页码这类小块墨迹
    ink[ink.sum(axis=1) > 0.5 * band.shape[1], :] = False
    ink[:, ink.sum(axis=0) > 0.6 * band.shape[0]] = False
    if int(ink.sum()) < min_ink:
        return None
    rows = np.where(ink.any(axis=1))[0]
    cols = np.where(ink.any(axis=0))[0]
    yy0, yy1 = max(0, rows[0] - 18), min(band.shape[0], rows[-1] + 18)
    xx0, xx1 = max(0, cols[0] - 30), min(band.shape[1], cols[-1] + 30)
    crop = Image.fromarray(band[yy0:yy1, xx0:xx1])
    s = 150.0 / max(1, crop.height)
    return crop.resize((max(1, int(crop.width * s)), 150))


def run(fitz, np, Image, ImageDraw, ImageFont, args) -> dict:
    outdir = args.out or os.path.dirname(os.path.abspath(args.paths[0]))
    os.makedirs(outdir, exist_ok=True)
    font = load_font(ImageFont)
    report = {"command": "footer-pageno", "out_dir": os.path.abspath(outdir), "files": []}

    for path in args.paths:
        if not os.path.isfile(path):
            sys.exit(f"[ERROR] 文件不存在: {path}")
        doc = fitz.open(path)
        tiles = [footer_tile(fitz, np, Image, doc, i, args.zoom, args.y0, args.y1, args.min_ink)
                 for i in range(doc.page_count)]
        total = doc.page_count
        doc.close()

        stem = os.path.splitext(os.path.basename(path))[0]
        # 单格宽度按**实际裁出来的墨迹块**定，但要设上限：个别页页脚区混进正文会把
        # bbox 撑得很宽，若不封顶，整张对照图会宽到看不清数字。
        max_tw = max((t.width for t in tiles if t is not None), default=260)
        tile_w = min(max(340, max_tw + 40), args.tile_max_w)
        sheets = []
        for part in range(0, total, args.rows):
            chunk = tiles[part:part + args.rows]
            canvas = Image.new("RGB", (tile_w * len(chunk), 150 + LABEL_H), (255, 255, 255))
            d = ImageDraw.Draw(canvas)
            for i, t in enumerate(chunk):
                x = i * tile_w
                d.rectangle((x, 0, x + tile_w - 1, LABEL_H - 1), fill=(0, 0, 0))
                d.text((x + 8, 12), f"page {part + i + 1}", fill=(255, 255, 0), font=font)
                d.rectangle((x, LABEL_H, x + tile_w - 1, LABEL_H + 149), outline=(190, 190, 190))
                if t is None:
                    d.text((x + 12, LABEL_H + 60), "no footer ink", fill=(0, 0, 200), font=font)
                else:
                    if t.width > tile_w - 20:          # 超宽块按比例缩小塞进格子
                        s2 = (tile_w - 20) / t.width
                        t = t.resize((tile_w - 20, max(1, int(t.height * s2))))
                    canvas.paste(t, (x + (tile_w - t.width) // 2, LABEL_H + (150 - t.height) // 2))
            fp = os.path.join(outdir, f"{stem}_footers_{part // args.rows + 1}.png")
            canvas.save(fp)
            sheets.append(os.path.abspath(fp))

        report["files"].append({
            "path": os.path.abspath(path),
            "pages": total,
            "tiles_with_ink": sum(1 for t in tiles if t),
            "tiles_without_ink": [i + 1 for i, t in enumerate(tiles) if t is None],
            "sheets": sheets,
        })
    return report


def main():
    p = argparse.ArgumentParser(
        prog="footer_pageno",
        description="把扫描件每页的页脚（印刷页码）裁出来拼成对照图，用于合并前判读真实页序",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python footer_pageno.py odd.pdf even.pdf\n"
            "  python footer_pageno.py odd.pdf --zoom 6 --y0 0.84 --y1 0.98 --out ./_footers\n"
            "  python footer_pageno.py merged.pdf --json\n"
        ),
    )
    p.add_argument("paths", nargs="+", help="一个或多个 PDF")
    p.add_argument("--out", help="对照图输出目录（默认与第一个输入同目录）")
    p.add_argument("--zoom", type=float, default=5.0, help="渲染放大倍数（默认 5.0，页码太小可加大）")
    p.add_argument("--y0", type=float, default=0.84, help="页脚区域上边界，占页高比例（默认 0.84）")
    p.add_argument("--y1", type=float, default=0.98, help="页脚区域下边界（默认 0.98）")
    p.add_argument("--rows", type=int, default=4, help="每张对照图放几页（默认 4；页数多可加大）")
    p.add_argument("--tile-max-w", type=int, default=520, metavar="PX",
                   help="单格最大宽度像素（默认 520），防止个别页撑宽整张图")
    p.add_argument("--min-ink", type=int, default=30, help="判定「有墨迹」的最少像素数（默认 30）")
    p.add_argument("--python", default=argparse.SUPPRESS, help="指定装有 fitz+numpy+pillow 的解释器")
    p.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 输出")
    args = p.parse_args()

    fitz, np, Image, ImageDraw, ImageFont = import_deps()
    res = run(fitz, np, Image, ImageDraw, ImageFont, args)

    if getattr(args, "json", False):
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"对照图目录: {res['out_dir']}")
        for f in res["files"]:
            print(f"  {os.path.basename(f['path'])}: {f['pages']} 页，"
                  f"{f['tiles_with_ink']} 页有页脚墨迹"
                  + (f"，无墨迹页 {f['tiles_without_ink']}" if f["tiles_without_ink"] else ""))
            for s in f["sheets"]:
                print(f"    {s}")


if __name__ == "__main__":
    main()
