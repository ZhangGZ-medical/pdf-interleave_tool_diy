#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selftest.py — pdf-interleave_tool_diy 自检脚本（不依赖任何真实数据）

自动生成合成的 odd/even 测试 PDF，然后端到端验证：
  1. 等页交叉合并 + 位图校验 + 文字顺序断言
  2. 页数不等（不丢页）与 --pad blank（补空白页）
  3. --first even 交换起始侧
  4. --drop-odd / --drop-even 修正偏移
  5. **--reverse-even / --reverse-odd 处理整侧倒序**，并断言
     「不倒序时 verify 仍报 ALL MATCH」这一校验盲区确实存在（回归保护）
  6. split 拆分后回拼校验（往返一致性）
  7. **反向测试**：人为打乱页序，verify 必须报 FAILED（防止校验器空转）
  8. 危险操作拦截：输出路径等于输入、两个输入同一文件
  9. footer_pageno.py 页脚对照图（有 numpy+Pillow 时才跑，否则 SKIP）

用法：
    python scripts/selftest.py            # 全部用例
    python scripts/selftest.py --keep     # 保留临时目录便于人工翻看
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "interleave_pdf.py")
FOOTER = os.path.join(HERE, "footer_pageno.py")

PASSED, FAILED = [], []


def check(name: str, cond: bool, detail: str = ""):
    (PASSED if cond else FAILED).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  <- {detail}" if detail and not cond else ""))


def run(args: list[str], py: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([py or sys.executable, SKILL] + args,
                          capture_output=True, text=True, encoding="utf-8")


def make_fixture(fitz, path: str, tag: str, pages: int, size=(595, 842)):
    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page(width=size[0], height=size[1])
        p.insert_text((72, 120), f"{tag}-{i + 1:02d}", fontsize=44)
    doc.save(path)
    doc.close()
    return path


def texts(fitz, path: str) -> list[str]:
    doc = fitz.open(path)
    out = [doc[i].get_text().strip() for i in range(doc.page_count)]
    doc.close()
    return out


def make_fixture_desc(fitz, path: str, tag: str, pages: int, size=(595, 842)):
    """与 make_fixture 同内容，但页序整体倒过来（模拟翻面重扫得到的倒序侧）。"""
    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page(width=size[0], height=size[1])
        p.insert_text((72, 120), f"{tag}-{pages - i:02d}", fontsize=44)
    doc.save(path)
    doc.close()
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="保留临时工作目录")
    ap.add_argument("--python", help="指定装有 PyMuPDF 的解释器")
    args = ap.parse_args()

    py = args.python
    probe = subprocess.run([py or sys.executable, "-c", "import fitz"])
    if probe.returncode != 0:
        sys.exit("当前解释器没有 PyMuPDF，请先 pip install pymupdf")

    import fitz  # noqa: E402

    tmp = tempfile.mkdtemp(prefix="pdf_interleave_selftest_")
    print(f"工作目录: {tmp}\n")

    odd = make_fixture(fitz, os.path.join(tmp, "odd.pdf"), "ODD", 9)
    even = make_fixture(fitz, os.path.join(tmp, "even.pdf"), "EVEN", 9)

    # ---------- 1. 等页交叉合并 ----------
    print("1. 等页交叉合并 (9 + 9)")
    merged = os.path.join(tmp, "merged.pdf")
    r = run(["merge", odd, even, "-o", merged, "--verify"], py)
    check("命令成功返回", r.returncode == 0, r.stdout + r.stderr)
    t = texts(fitz, merged)
    expect = [f"ODD-{i // 2 + 1:02d}" if i % 2 == 0 else f"EVEN-{i // 2 + 1:02d}" for i in range(18)]
    check("输出 18 页", len(t) == 18, f"实际 {len(t)}")
    check("页序 = ODD1,EVEN1,ODD2,EVEN2,...", t == expect, f"实际 {t[:6]}...")
    check("位图校验 ALL MATCH", "ALL MATCH" in r.stdout, r.stdout)

    # ---------- 2. 页数不等 ----------
    print("\n2. 页数不等 (10 + 7)")
    odd10 = make_fixture(fitz, os.path.join(tmp, "odd10.pdf"), "ODD", 10)
    even7 = make_fixture(fitz, os.path.join(tmp, "even7.pdf"), "EVEN", 7)
    m_un = os.path.join(tmp, "unequal.pdf")
    r = run(["merge", odd10, even7, "-o", m_un], py)
    t = texts(fitz, m_un)
    check("不丢页：输出 17 页", len(t) == 17, f"实际 {len(t)}")
    check("尾部提示存在", "tail_note" in r.stdout or "未丢页" in r.stdout, r.stdout)
    check("全部 17 页内容齐全",
          sorted(t) == sorted([f"ODD-{i+1:02d}" for i in range(10)] + [f"EVEN-{i+1:02d}" for i in range(7)]))

    m_pad = os.path.join(tmp, "padded.pdf")
    r = run(["merge", odd10, even7, "-o", m_pad, "--pad", "blank", "--verify"], py)
    t = texts(fitz, m_pad)
    check("--pad blank：输出 20 页", len(t) == 20, f"实际 {len(t)}")
    check("补的是空白页而非内容", t.count("") == 3, f"空白页 {t.count('')} 个")
    check("补白后校验 ALL MATCH", "ALL MATCH" in r.stdout, r.stdout)

    # ---------- 3. --first even ----------
    print("\n3. --first even（让偶数页那一路打头）")
    m_fe = os.path.join(tmp, "firsteven.pdf")
    r = run(["merge", odd, even, "-o", m_fe, "--first", "even", "--verify"], py)
    t = texts(fitz, m_fe)
    check("第 1 页来自 even", t[0] == "EVEN-01", f"实际 {t[0]}")
    check("第 2 页来自 odd", t[1] == "ODD-01", f"实际 {t[1]}")

    # ---------- 4. 偏移修正 ----------
    print("\n4. --drop-even 1（丢掉 even 首页后重新配对）")
    m_dr = os.path.join(tmp, "dropped.pdf")
    r = run(["merge", odd, even, "-o", m_dr, "--drop-even", "1", "--verify"], py)
    t = texts(fitz, m_dr)
    check("输出 17 页", len(t) == 17, f"实际 {len(t)}")
    check("even 首页已被剔除", "EVEN-01" not in t, str(t[:4]))

    # ---------- 5. 整侧倒序 ----------
    print("\n5. 整侧倒序（翻面重扫最常见的坑）")
    even_desc = make_fixture_desc(fitz, os.path.join(tmp, "even_desc.pdf"), "EVEN", 9)
    check("倒序侧构造正确（首页应为 EVEN-09）",
          texts(fitz, even_desc)[0] == "EVEN-09", str(texts(fitz, even_desc)[:3]))

    # 5a. 不倒序直接合 —— 页面结构看起来对，verify 却照样 ALL MATCH（盲区）
    m_naive = os.path.join(tmp, "naive_desc.pdf")
    r = run(["merge", odd, even_desc, "-o", m_naive, "--verify"], py)
    nv = texts(fitz, m_naive)
    check("盲区确认：不倒序时 verify 仍报 ALL MATCH", "ALL MATCH" in r.stdout, r.stdout[:300])
    check("盲区确认：但页序其实是错的（第 2 页 = EVEN-09）",
          nv[1] == "EVEN-09", f"实际 {nv[:4]}")

    # 5b. 加 --reverse-even 后应还原成正确页序
    m_rev = os.path.join(tmp, "rev_even.pdf")
    r = run(["merge", odd, even_desc, "-o", m_rev, "--reverse-even", "--verify"], py)
    check("--reverse-even 命令成功返回", r.returncode == 0, r.stdout + r.stderr)
    t = texts(fitz, m_rev)
    check("输出 18 页", len(t) == 18, f"实际 {len(t)}")
    check("页序恢复 = ODD1,EVEN1,ODD2,EVEN2,...", t == expect, f"实际 {t[:6]}...")
    check("位图校验 ALL MATCH", "ALL MATCH" in r.stdout, r.stdout)
    check("输出里标出倒序侧", "reversed: even" in r.stdout, r.stdout[:400])

    # 5c. verify 子命令也要认得倒序侧
    r = run(["verify", m_rev, "--odd", odd, "--even", even_desc, "--reverse-even"], py)
    check("verify --reverse-even 通过", r.returncode == 0 and "ALL MATCH" in r.stdout, r.stdout[:300])
    r = run(["verify", m_rev, "--odd", odd, "--even", even_desc], py)
    check("verify 漏传 --reverse-even 时判 FAILED", r.returncode == 2, r.stdout[:300])

    # 5d. --reverse-odd 与 --drop-* 叠加：先丢开头 N 页，再整体倒序
    odd_desc = make_fixture_desc(fitz, os.path.join(tmp, "odd_desc.pdf"), "ODD", 9)
    # 倒序后 [ODD-09..ODD-01]，丢掉（文件顺序的）首 1 页 = ODD-09，再倒序 => ODD-01..ODD-08（8 页）
    # even 仍 9 页，故 8 对 + 末尾多出的 EVEN-09 = 17 页
    m_ro = os.path.join(tmp, "rev_odd_drop.pdf")
    r = run(["merge", odd_desc, even, "-o", m_ro,
             "--reverse-odd", "--drop-odd", "1", "--verify"], py)
    t = texts(fitz, m_ro)
    check("--reverse-odd + --drop-odd 输出 17 页", len(t) == 17, f"实际 {len(t)}")
    check("首两页为 ODD-01 / EVEN-01", t[:2] == ["ODD-01", "EVEN-01"], f"实际 {t[:2]}")
    check("末页是 even 多出的 EVEN-09", t[-1] == "EVEN-09", f"实际 {t[-1]}")
    check("被丢掉的 ODD-09 不在结果里", "ODD-09" not in t, str(t))

    # ---------- 6. split 往返 ----------
    print("\n6. split 往返一致性")
    outdir = os.path.join(tmp, "split")
    r = run(["split", merged, "-o", outdir, "--verify"], py)
    check("split 成功", r.returncode == 0, r.stdout + r.stderr)
    so = os.path.join(outdir, "merged_odd.pdf")
    se = os.path.join(outdir, "merged_even.pdf")
    check("生成 odd/even 两个文件", os.path.isfile(so) and os.path.isfile(se))
    check("odd 文件 9 页", fitz.open(so).page_count == 9)
    check("even 文件 9 页", fitz.open(se).page_count == 9)
    check("拆分内容与源一致", texts(fitz, so) == texts(fitz, odd) and texts(fitz, se) == texts(fitz, even))

    # ---------- 7. 反向测试：校验器必须能报错 ----------
    print("\n7. 反向测试：人为错序必须被 verify 判定失败")
    bad = os.path.join(tmp, "bad.pdf")
    run(["merge", even, odd, "-o", bad], py)          # 位置参数反着传 => 等效 --first even
    check("位置参数反传与 --first even 结果一致",
          texts(fitz, bad) == texts(fitz, m_fe))
    r = run(["verify", bad, "--odd", odd, "--even", even], py)
    check("错序被检出（verdict=FAILED）", "FAILED" in r.stdout, r.stdout)
    check("错序时退出码为 2", r.returncode == 2, f"exit={r.returncode}")

    # ---------- 8. 危险操作拦截 ----------
    print("\n8. 危险操作拦截")
    r = run(["merge", odd, even, "-o", odd], py)
    check("拒绝覆盖输入文件", r.returncode != 0 and "覆盖" in r.stdout, r.stdout)
    r = run(["merge", odd, odd, "-o", os.path.join(tmp, "x.pdf")], py)
    check("拒绝两个输入相同", r.returncode != 0 and "同一个文件" in r.stdout, r.stdout)

    # ---------- 9. CLI 形态与 JSON ----------
    print("\n9. CLI：--json 前置/后置、info")
    r1 = run(["merge", odd, even, "-o", os.path.join(tmp, "j1.pdf"), "--json"], py)
    r2 = run(["--json", "merge", odd, even, "-o", os.path.join(tmp, "j2.pdf")], py)
    check("--json 写在子命令之后可用", '"output_pages": 18' in r1.stdout, r1.stdout[:200])
    check("--json 写在子命令之前也可用", '"output_pages": 18' in r2.stdout, r2.stdout[:200])
    r = run(["info", odd, even, "--json"], py)
    check("info --json 正常", '"pages": 9' in r.stdout, r.stdout[:200])

    # ---------- 10. footer_pageno：合并前的页脚判读 ----------
    print("\n10. footer_pageno 页脚对照图（前置判读）")
    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
        has_pil_np = True
    except ImportError:
        has_pil_np = False
    if not has_pil_np:
        print("  [SKIP] 当前解释器缺 numpy/Pillow，跳过（脚本自身会自动换解释器）")
    else:
        fdir = os.path.join(tmp, "footers")
        r = subprocess.run([py or sys.executable, FOOTER, odd, even_desc,
                            "--out", fdir, "--json"],
                           capture_output=True, text=True, encoding="utf-8")
        check("footer_pageno 成功返回", r.returncode == 0, r.stdout + r.stderr)
        check("JSON 报了页数与目标目录",
              '"pages": 9' in r.stdout and '"out_dir"' in r.stdout, r.stdout[:300])
        pngs = [f for f in os.listdir(fdir) if f.endswith(".png")] if os.path.isdir(fdir) else []
        # 两个输入文件 × 各 9 页、每 4 页一张 => 2 × 3 = 6 张
        check("生成了对照图 PNG（2 文件 × 3 张 = 6 张）", len(pngs) == 6, str(sorted(pngs)))

    print("\n" + "=" * 62)
    print(f"合计 {len(PASSED) + len(FAILED)} 项：PASS {len(PASSED)} / FAIL {len(FAILED)}")
    if FAILED:
        print("失败项：")
        for f in FAILED:
            print("  -", f)
    if not args.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print("临时目录保留在:", tmp)
    print("=" * 62)
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
