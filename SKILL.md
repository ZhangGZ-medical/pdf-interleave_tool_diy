---
name: pdf-interleave_tool_diy
description: >
  奇数页/偶数页 PDF 交叉合并工具（interleave / de-interleave）。把「只剩奇数页的
  odd.pdf」与「只剩偶数页的 even.pdf」按 1,2,3,4… 的真实页序重新拼成一份完整 PDF，
  并可用页面位图哈希逐页证明页序正确。同时支持反向拆分（把完整 PDF 拆成
  odd/even 两个文件）。

  当用户出现以下情况时使用：
  - 有一对 odd/even（或"奇数页/偶数页"、"单页/双页"、"正面/反面"）PDF，要合成一份
  - 双面打印后翻面重新扫描，得到两个只含单数页/双数页的文件，需要还原装订顺序
  - 扫描仪"奇偶页分离"输出（scan front/back、duplex split）需要重新合并
  - 要验证一份交叉合并件到底有没有串页、错页、缺页

  触发词示例：
  - "把 odd 和 even 交叉合并"
  - "奇数页和偶数页合并成一个 PDF"
  - "奇偶页合并" / "交叉合并PDF" / "interleave"
  - "把扫描的正反面合成一份"
  - "把这个 PDF 拆成奇数页和偶数页"
  - "校验合并后的页序对不对"
  - "odd.pdf even.pdf merge"

  能力说明：
  - merge：交叉合并，页数不等时默认不丢页；可选补空白页保持奇偶配对
  - split：把完整 PDF 拆成奇数页/偶数页两个文件（merge 的逆操作）
  - verify：以页面位图 md5 逐页校验合并结果，输出 ALL MATCH / FAILED
  - info：只看页数、页面尺寸、文件大小，不写任何文件
  - 支持 --first 指定打头的一侧、--drop-odd/--drop-even 修正 ±N 页偏移
  - 输出 JSON（--json）便于程序串联；退出码 0=一致、2=校验失败、1=参数或IO错误
version: 1.0.0
base_dir: C:\Users\G1381\.workbuddy\skills\pdf-interleave_tool_diy
---

# pdf-interleave_tool_diy — 奇偶页 PDF 交叉合并 / 拆分 / 校验

## 这个技能解决什么问题

打印机和扫描仪最爱制造一种残废文件：**一份文档被劈成两个 PDF，一个只含奇数页
（1,3,5…），一个只含偶数页（2,4,6…）**。典型来源：

- 双面打印：先打奇数页 → 翻面 → 打偶数页，扫描时两份分开
- 扫描仪"奇偶页分离 / 前后页分别输出"模式
- 装订厂/影印店把内页按正反面分开扫描后交回

拿到的结果是**两份都不完整**，任何一份单独看都是残本。必须交叉合并才能还原成
1,2,3,4… 的可读顺序，而且**合完之后必须证明页序没错**——错页的 PDF 比残本更危险，
因为它看起来是完整的。

本技能就是这两件事：**合并**（merge）与**证明合并正确**（verify）。

## 核心工作流程（SOP）

### Step 1 — 先看清单侧页数，别急着合

```bash
python scripts/interleave_pdf.py info odd.pdf even.pdf
```

输出页数、页面尺寸分布、文件大小。判断要点：

| 观察到的现象 | 说明 | 对应做法 |
|---|---|---|
| 两侧页数相等 | 标准情况 | 直接 merge |
| 两侧差 1 页，且奇数侧多 | 最后一张单面页，正常 | 默认合并（尾页原样追加） |
| 两侧差得多 / 尺寸分布不一致 | 可能缺页或混了别的扫描 | 先人工翻页确认再合 |
| 页面尺寸不唯一（非 uniform） | 中间混入了不同规格的页 | 先排查来源 |

### Step 2 — 合并

```bash
python scripts/interleave_pdf.py merge odd.pdf even.pdf -o merged.pdf --verify
```

- `--verify` **强烈建议常开**：几秒的代价换来"逐页位图哈希全部匹配"的硬证据。
- 输出文件路径**不允许**等于任一输入文件，脚本会直接拒绝（防止覆盖原始数据）。

### Step 3 — 读校验结论

```
verify:
  checked_pages: 18
  mismatches: 0
  verdict: ALL MATCH        <- 只有这一行才算通过
```

`verdict: FAILED` 时退出码为 `2`，`detail` 会列出第几页应该来自哪个源文件的第几页。

### Step 4 — 人工抽查头两页

自动校验能证明"页序与源文件一致"，但**证明不了源文件本身分对了**。打开合并件
翻第 1、2 页，看正文是否连得上（比如页脚页码 1、2）。若发现整体错位 N 页，用
`--drop-odd/--drop-even` 修正，见下节。

## 命令行参考

### merge

```
python scripts/interleave_pdf.py merge ODD EVEN -o OUT [选项]
```

| 选项 | 默认 | 说明 |
|---|---|---|
| `-o, --output` | 必填 | 输出的新 PDF 路径 |
| `--first {odd,even}` | `odd` | 合并件第 1 页取自哪一路。`merge A B --first even` 等价于 `merge B A` |
| `--drop-odd N` | `0` | 跳过 odd 文件开头的 N 页（修正 ±N 错位） |
| `--drop-even N` | `0` | 跳过 even 文件开头的 N 页 |
| `--pad {none,blank}` | `none` | 页数不等时：`none`=尾页原样追加（**不丢页**）；`blank`=补空白页保持奇偶配对 |
| `--verify` | 关 | 合并后逐页位图比对 |
| `--no-overwrite` | 关 | 输出已存在时拒绝覆盖 |
| `--json` | 关 | JSON 输出（可写在子命令前或后） |

**`--pad blank` 什么时候用**：当"缺页"发生在中间而不是末尾时（例如偶数侧少了第 6 页），
补齐空白页能让**后续所有页面继续两两配对**；否则从缺页处开始，后文全部错位一页。
代价是页数变多、留一个可见空页。默认 `none` 优先保证不丢数据。

### split（merge 的逆操作）

```
python scripts/interleave_pdf.py split MERGED.pdf -o OUTDIR [--prefix odd,even] [--verify]
```

第 1,3,5… 页写入 `<stem>_odd.pdf`，第 2,4,6… 页写入 `<stem>_even.pdf`。
`--verify` 会把拆分结果**回拼一遍**并与原件比对，用于确认拆分无损。

典型用途：手上只有合并件、但需要按"先打奇数页再翻面打偶数页"重新打印时，
先 split 出两份再交给打印机。

### verify

```
python scripts/interleave_pdf.py verify MERGED.pdf --odd ODD.pdf --even EVEN.pdf
```

单独校验已有的合并件，参数语义与 merge 完全一致（含 `--first` / `--drop-*` / `--pad`）。

### info

```
python scripts/interleave_pdf.py info a.pdf b.pdf ...
```

只读，不产生任何输出文件。

## 校验原理（为什么这个校验可信）

1. 每页按 72 dpi 渲染成位图，对 `宽x高|通道数` + 像素数据取 md5。
2. 把合并件每一页的哈希，与"它应该来自的那个源文件的对应页"哈希逐一比对。
3. 全部相等 → `ALL MATCH`；任何一页不符 → 记录 `第 N 页 期望=odd[7] 实际=内容不符`。

这比对的是**渲染后的像素**，因此能同时抓住：页序错、内容被替换、页面被旋转/裁切、
页面尺寸被改、以及填充页其实不是空白等情况。

**反向测试已内置**：`scripts/selftest.py` 里专门构造了一份错序文件，要求 verify 必须
报 FAILED。校验器不会因为"总是通过"而给出虚假安全感。

## 依赖与运行

- **PyMuPDF**（import 名 `fitz`）：`pip install pymupdf`
- Python 3.8+（用到了 `from __future__ import annotations`，3.8 起可用）
- 无其他第三方依赖（其余全是标准库）

**解释器自举**：本机 managed 裸解释器里没有 PyMuPDF。脚本在 `import fitz` 失败时会
自动在以下位置寻找可用解释器并用子进程重跑，因此**用哪个 python 启动都能跑起来**：

1. 环境变量 `PDF_INTERLEAVE_PYTHON`
2. 命令行 `--python <路径>`
3. `%USERPROFILE%\.workbuddy\binaries\python\envs\*\Scripts\python.exe`（本机实测命中）
4. miniconda3 / anaconda3 常见路径

已实测：用**无 fitz 的裸解释器**启动，脚本自动切到 `envs\default` 解释器并正常完成。

## 自检

```bash
python scripts/selftest.py          # 27 项断言，全部合成数据，不碰真实文件
python scripts/selftest.py --keep   # 保留临时目录，便于人工翻看产物
```

覆盖：等页合并页序、页数不等不丢页、`--pad blank` 空白页判定、`--first even`、
`--drop-even` 偏移修正、split 往返一致、**错序必须被检出**、危险操作拦截、CLI 参数位置。

## 踩坑记录

| 现象 | 原因 | 处理 |
|---|---|---|
| `FileNotFoundError` 中文路径 | Git Bash 下把 `/d/xxx` 形式路径传给 Python（Windows 不认） | 统一传 `D:\...` 反斜杠路径；或先 `cd` 再传相对路径 |
| `unrecognized arguments: --json` | `--json` 原先只挂在主解析器上，写在子命令后失效 | 已修：`--json`/`--python` 用 `parents=[common]` + `default=SUPPRESS`，前后位置都能写 |
| 子解析器把主解析器的值覆盖回默认 | argparse 子解析器默认值会覆盖同名主参数 | 关键参数一律用 `argparse.SUPPRESS` 作默认值 |
| 输出路径误写成输入文件 | 手滑 | 脚本硬拦截：输出==任一输入 → 直接报错退出 |
| 合完发现整体错位一页 | 源文件本身起页就不是文档第 1 页（翻面扫描常见） | 用 `--drop-odd/--drop-even N` 去掉多余的前导页后重合并 |
| 校验说 ALL MATCH 但内容仍不对 | 校验证明的是"与源文件一致"，不是"源文件分对了" | 人工翻第 1、2 页看正文是否连得上 |

## 文件结构

```
pdf-interleave_tool_diy/
├── SKILL.md                  # 本文件（技能定义）
├── README.md                 # 面向使用者的说明
├── requirements.txt          # pymupdf
└── scripts/
    ├── interleave_pdf.py     # 主脚本（merge / split / verify / info）
    └── selftest.py           # 27 项自检，含必须失败的反向测试
```

## 实测案例（2026-09-14）

`09_参考资料` 下的伦理批件扫描件被劈成 odd.pdf（9 页）与 even.pdf（9 页）：

```
info   → odd 9 页 / even 9 页，两侧均为 596x841 pt（A4），尺寸 uniform
merge  → 18 页，17.3 MB，verify: checked_pages=18 / mismatches=0 / ALL MATCH
```

随后做往返验证：把成品 split 回 odd/even，再 merge 一次，与原件**逐页位图 md5 比对
零差异**（18/18 页一致，`ROUNDTRIP OK`）。
