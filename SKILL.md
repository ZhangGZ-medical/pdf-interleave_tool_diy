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
  - **一路是正面扫描、一路是反面（背面）扫描**，需要合并（反面那一路必然是倒序）
  - 扫描仪"奇偶页分离"输出（scan front/back、duplex split）需要重新合并
  - 合并出来**页码乱序/忽大忽小**，或某一侧是**倒序**（页码递减）需要还原
  - 扫描件没有文字层、想确认每页纸上印的**真实页码**以判断合并顺序对不对
  - 要验证一份交叉合并件到底有没有串页、错页、缺页

  触发词示例：
  - "把 odd 和 even 交叉合并"
  - "奇数页和偶数页合并成一个 PDF"
  - "奇偶页合并" / "交叉合并PDF" / "interleave"
  - "把扫描的正反面合成一份"
  - "even 是反面扫描 / 背面扫描，是倒序的"
  - "从后往前抽页合并"
  - "合并后页码乱了 / 页序不对"
  - "把这个 PDF 拆成奇数页和偶数页"
  - "校验合并后的页序对不对"
  - "odd.pdf even.pdf merge"

  能力说明：
  - merge：交叉合并，页数不等时默认不丢页；可选补空白页保持奇偶配对
  - split：把完整 PDF 拆成奇数页/偶数页两个文件（merge 的逆操作）
  - verify：以页面位图 md5 逐页校验合并结果，输出 ALL MATCH / FAILED
  - footer_pageno：合并前生成**页脚页码对照图**，一眼看出哪一侧是倒序/重号/缺号
    （纯扫描件无文字层也适用，不做 OCR）
  - info：只看页数、页面尺寸、文件大小，不写任何文件
  - 支持 --first 指定打头的一侧、--drop-odd/--drop-even 修正 ±N 页偏移、
    --reverse-odd/--reverse-even 处理**反面扫描导致的整侧倒序**
  - **关键规律**：反面（背面）扫描得到的那一路，页序**物理上必然是倒序**——
    一叠纸翻面后，原来最底下那张变成最上面，于是页码从最后一页往回走
  - **重要认知**：两侧页数相等 + verify 报 ALL MATCH 都**不能**证明合对了；
    只有读印刷页码（Step 1.5）才能判断源文件分页是否正确
  - 输出 JSON（--json）便于程序串联；退出码 0=一致、2=校验失败、1=参数或IO错误
version: 1.1.0
base_dir: C:\Users\G1381\.workbuddy\skills\pdf-interleave_tool_diy
---

# pdf-interleave_tool_diy — 奇偶页 PDF 交叉合并 / 拆分 / 校验

## 这个技能解决什么问题

打印机和扫描仪最爱制造一种残废文件：**一份文档被劈成两个 PDF，一个只含奇数页
（1,3,5…），一个只含偶数页（2,4,6…）**。典型来源：

- 双面打印：先打奇数页 → 翻面 → 打偶数页，扫描时两份分开
- 扫描仪"奇偶页分离 / 前后页分别输出"模式
- 装订厂/影印店把内页按正反面分开扫描后交回
- **翻面重扫：一路是正面扫描、另一路是反面扫描**

拿到的结果是**两份都不完整**，任何一份单独看都是残本。必须交叉合并才能还原成
1,2,3,4… 的可读顺序，而且**合完之后必须证明页序没错**——错页的 PDF 比残本更危险，
因为它看起来是完整的。

本技能是三件事：**判读页序**（footer_pageno）→ **合并**（merge）→ **证明合并正确**（verify）。

> ⚠️ 最容易踩的坑：**"两份页数一样" ≠ "可以合"**。`info` 页数相等、`verify` 报 ALL MATCH，
> 都可能出现在错误结果上。合并前先读一遍纸上印的页码，见 Step 1.5。

### 反面扫描拿到的一定是倒序（物理必然，不是偶然）

这条要当**规律**用，遇到"一路正面、一路反面"就先把反面那一路按倒序处理：

一叠纸正面朝上放进进纸器扫一遍 → 得到正序。把这叠纸**整摞翻面**再扫一遍，
原来压在**最底下**的那张翻到了最上面，于是背面的页序从**最后一页开始往回走** ——
扫出来的必然是倒序。

以一份 **12 页**双面文档（两面印满）为例：

| 手上这一路是 | 页序 | 典型页码表现 |
|---|---|---|
| 正面扫描 | **正序**（递增） | 1、3、5、7、9、11 |
| **反面扫描** | **倒序**（递减） | 12、10、8、6、4、2 |

> 页码的**起始值和步长随原稿而变**（原稿若从第 5 页起、或中途夹了不编号的附件页，
> 就不会是干净的 1/3/5…）。判据只看**单调方向**：递增=正面，递减=反面。

**做法**：确认某一路是反面扫描后，**不要先合完再看结果**，直接在 merge 时加倒序开关，
再用 `footer_pageno.py` 读一遍页码确认单调递增即可：

```bash
# 例：even.pdf 是反面扫描 → 倒序
python scripts/interleave_pdf.py merge odd.pdf even.pdf -o merged.pdf --reverse-even --verify
```

> 若拿不准哪一路是反面：`footer_pageno.py` 一读便知——页码递减的那一路就是它。

## 核心工作流程（SOP）

### Step 1 — 先看清单侧页数，别急着合

```bash
python scripts/interleave_pdf.py info odd.pdf even.pdf
```

输出页数、页面尺寸分布、文件大小。判断要点：

| 观察到的现象 | 说明 | 对应做法 |
|---|---|---|
| 两侧页数相等 | **注意：这不能说明可以直接合** | 仍需做 Step 1.5 的页序判读 |
| 两侧差 1 页，且奇数侧多 | 最后一张单面页，正常 | 页序判读通过后 merge（尾页原样追加） |
| 两侧差得多 / 尺寸分布不一致 | 可能缺页或混了别的扫描 | 先人工翻页确认再合 |
| 页面尺寸不唯一（非 uniform） | 中间混入了不同规格的页 | 先排查来源 |

### Step 1.5 — 判读印刷页码：确认两侧真是同一文档的奇偶页（**别跳过**）

`info` 页数相等 + `merge --verify` 报 ALL MATCH，**都不代表可以合**。`verify` 只证明
「输出页与它声称的来源页一致」，它默认来源分页是对的；一旦来源本身就错了，它会照样
给出 ALL MATCH 的假安全感。**唯一可靠的判据是纸上印的页码。**

```bash
python scripts/footer_pageno.py odd.pdf even.pdf        # 生成页脚对照图，肉眼读页码
```

产出形如 `odd_footers_1.png`、`even_footers_1.png`（默认每 4 页一张，页脚数字已自动裁切放大、
每格标了 `page N`）。判读规则：

| 读到的页序 | 含义 | 做法 |
|---|---|---|
| **一侧递增、另一侧递减** | 递减那侧是**反面（背面）扫描**，物理上必然倒序 | merge 时加 `--reverse-odd` / `--reverse-even` |
| 两侧各自递增、且页号互补 | 两侧都是正面扫描（或仪器已自行排好） | 直接 merge |
| 同一页号出现两次 | 重复扫描页（原稿重号，或重复扫了一张） | 先确认留哪一张，再决定丢弃 |
| 出现 NONE | 该页没印页码（附件首页/空白背面常见） | 结合上下文判断，必要时放大 `--zoom` 或用 `--y0/--y1` 调区间 |
| 页码不互补（有断号、有重号、两侧都对不上） | **不是一份文档的奇偶对** | 别用 `--first`/`--drop-*` 硬凑，按印刷页码写自定义页序重建，见下节 |

**倒序判据（本次实测）**：`even.pdf` 是**反面扫描**，页码 16、14、12、10、… 递减；
`odd.pdf` 是正面扫描，页码 5、6、8、…、15 递增 → 只加一个 `--reverse-even` 就一次合对。

```bash
python scripts/interleave_pdf.py merge odd.pdf even.pdf -o merged.pdf --reverse-even --verify
```

> `--drop-*` 与 `--reverse-*` 可叠加，执行顺序是**先按文件顺序丢掉开头 N 页，再整体倒序**。

### Step 1.6 — 两侧不是干净的奇偶拆分时：按印刷页码重建

如果两侧页码不互补（有重号、有断号、或多出夹页），**不要**用 `--first/--drop-*` 反复试凑，
那只会产出「看起来完整、其实错序」的文件。正确做法是按印刷页码写死一条页序，逐页复制重建：

```python
# ORDER = [(来源, 0基页号), ...]，按纸上印的页码从小到大排
out = fitz.open()
for key, idx in ORDER:
    out.insert_pdf(src[key], from_page=idx, to_page=idx)
out.save(dest, deflate=True, garbage=4)
```

重建后**必须逐页复核**（渲染 72 dpi 取像素 md5，与"它应该来自的那一页"比对），
不能只用 `merge --verify`。

### Step 2 — 合并

```bash
python scripts/interleave_pdf.py merge odd.pdf even.pdf -o merged.pdf --verify
```

- `--verify` **强烈建议常开**：几秒的代价换来"逐页位图哈希全部匹配"的硬证据。
- 输出文件路径**不允许**等于任一输入文件，脚本会直接拒绝（防止覆盖原始数据）。
- 若 Step 1.5 判定某侧整体倒序，在这一步补上 `--reverse-odd` / `--reverse-even`。

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
翻第 1、2 页，看正文是否连得上（比如页脚页码 5、6 是否连续递增）。若整份页码
单调递增即通过；若发现递增/递减异常或整段错位，用 `--drop-*` / `--reverse-*` 修正。

> **verify 的边界（务必记住）**：它比对的是「输出第 N 页」与「映射表说它该来自的那一页」。
> 映射表本身错了（比如 even 其实是倒序、或两侧页码不互补），它一样给 ALL MATCH。
> 所以 **Step 1.5 的印刷页码判读不能省**；`selftest.py` 里专门有一条断言固化这个盲区。

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
| `--reverse-odd` | 关 | odd 那一路**整体倒序**取页（该路是**反面/背面扫描**时用这个） |
| `--reverse-even` | 关 | even 那一路**整体倒序**取页（同上——反面扫描的页序物理上必然倒置） |
| `--pad {none,blank}` | `none` | 页数不等时：`none`=尾页原样追加（**不丢页**）；`blank`=补空白页保持奇偶配对 |
| `--verify` | 关 | 合并后逐页位图比对 |
| `--no-overwrite` | 关 | 输出已存在时拒绝覆盖 |
| `--json` | 关 | JSON 输出（可写在子命令前或后） |

**`--drop-*` 与 `--reverse-*` 的叠加顺序**：先按文件顺序丢掉开头 N 页，再整体倒序。
例如"反面那一路最前面多扫了一张封皮" → `--reverse-even --drop-even 1`。

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

单独校验已有的合并件，参数语义与 merge 完全一致
（含 `--first` / `--drop-*` / `--reverse-*` / `--pad`）。

### footer_pageno（**合并前**的页序判读）

```
python scripts/footer_pageno.py ODD.pdf EVEN.pdf [--out DIR] [--zoom 5] [--y0 0.84] [--y1 0.98] [--rows 4]
```

把每个 PDF 每页的页脚区域自动裁切、放大、按页编号拼成对照图（`<stem>_footers_N.png`），
由人一眼读出印刷页码。**不做 OCR**，也不需要文字层——扫描件同样适用。

| 参数 | 默认 | 说明 |
|---|---|---|
| `--out` | 与第一个输入同目录 | 对照图输出目录 |
| `--zoom` | `5.0` | 渲染放大倍数，页码太小就加大 |
| `--y0 / --y1` | `0.84 / 0.98` | 页脚区域占页高的比例区间 |
| `--rows` | `4` | 每张对照图放几页（放宽了数字会看不清） |
| `--tile-max-w` | `520` | 单格最大宽度 px；个别页页脚区混进正文会把块撑宽，靠它封顶 |
| `--min-ink` | `30` | 判定「有墨迹」的最少像素数 |

判定表见 Step 1.5。依赖 `fitz + numpy + Pillow`（脚本自带解释器自举，与主脚本同一套逻辑）。

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

### 它证明不了什么（边界，必须知道）

`verify` 的比对基准是**映射表**（"第 N 页取自 odd[7]"）。映射表由 `--first / --drop-* /
--reverse-*` 这些参数推出来 —— **如果源文件本身分错了（例如 even 其实是倒序、
或两侧页码根本不互补），映射表就是错的，verify 照样报 ALL MATCH。**

所以：`info` 页数相等 + `--verify` ALL MATCH ≠ 合并正确。**判定源文件分页是否合理，
只能靠 Step 1.5 读印刷页码。**

**反向测试已内置**：`scripts/selftest.py` 里构造了错序文件要求 verify 必须报 FAILED；
并额外固化了一条断言——「even 倒序但不加 `--reverse-even` 时，verify 仍报 ALL MATCH」，
把上面这个盲区长期钉在回归测试里。

## 依赖与运行

- **PyMuPDF**（import 名 `fitz`）：`pip install pymupdf`
- `footer_pageno.py` 额外需要 **numpy + Pillow**：`pip install numpy pillow`
- Python 3.8+（用到了 `from __future__ import annotations`，3.8 起可用）

**解释器自举**：本机 managed 裸解释器里没有 PyMuPDF。脚本在 `import fitz` 失败时会
自动在以下位置寻找可用解释器并用子进程重跑，因此**用哪个 python 启动都能跑起来**：

1. 环境变量 `PDF_INTERLEAVE_PYTHON`
2. 命令行 `--python <路径>`
3. `%USERPROFILE%\.workbuddy\binaries\python\envs\*\Scripts\python.exe`（本机实测命中）
4. miniconda3 / anaconda3 常见路径

已实测：用**无 fitz 的裸解释器**启动，脚本自动切到 `envs\default` 解释器并正常完成。

## 自检

```bash
python scripts/selftest.py          # 44 项断言，全部合成数据，不碰真实文件
python scripts/selftest.py --keep   # 保留临时目录，便于人工翻看产物
```

覆盖：等页合并页序、页数不等不丢页、`--pad blank` 空白页判定、`--first even`、
`--drop-even` 偏移修正、**`--reverse-even` / `--reverse-odd` 整侧倒序还原**、
**「倒序侧不倒序时 verify 仍报 ALL MATCH」的盲区断言**、`--reverse-*` 与 `--drop-*` 叠加、
split 往返一致、**错序必须被检出**、危险操作拦截、CLI 参数位置、`footer_pageno` 出图。

## 踩坑记录

| 现象 | 原因 | 处理 |
|---|---|---|
| `FileNotFoundError` 中文路径 | Git Bash 下把 `/d/xxx` 形式路径传给 Python（Windows 不认） | 统一传 `D:\...` 反斜杠路径；或先 `cd` 再传相对路径 |
| `unrecognized arguments: --json` | `--json` 原先只挂在主解析器上，写在子命令后失效 | 已修：`--json`/`--python` 用 `parents=[common]` + `default=SUPPRESS`，前后位置都能写 |
| 子解析器把主解析器的值覆盖回默认 | argparse 子解析器默认值会覆盖同名主参数 | 关键参数一律用 `argparse.SUPPRESS` 作默认值 |
| 输出路径误写成输入文件 | 手滑 | 脚本硬拦截：输出==任一输入 → 直接报错退出 |
| 合完发现整体错位一页 | 源文件本身起页就不是文档第 1 页（翻面扫描常见） | 用 `--drop-odd/--drop-even N` 去掉多余的前导页后重合并 |
| **合完发现页码忽大忽小、整体乱序** | **该侧是反面扫描**——一叠纸翻面后页序物理上必然倒置（`info` 页数相等、`verify` 也报 ALL MATCH，完全看不出问题） | 先用 `footer_pageno.py` 读页码；反面那一路加 `--reverse-odd` / `--reverse-even` 重合并 |
| 校验说 ALL MATCH 但内容仍不对 | 校验证明的是"与映射表一致"，不是"源文件分对了" | 读印刷页码（Step 1.5）；页码非单调递增就说明合并顺序错 |
| 两侧页码不互补（有重号/断号/多出夹页） | 根本不是一份文档的奇偶对（常见于扫描时混入重复页、空白背面、别的附件页） | 不要用 `--first/--drop-*` 硬凑；按印刷页码写自定义页序重建（Step 1.6），并逐页 md5 复核 |
| `footer_pageno` 报 `ImageFont has no attribute getmask` | 把 `ImageFont` **模块**当字体对象传给了 `ImageFont.truetype` 的 `font=` 参数 | 已修：先 `load_font()` 取字体对象再传 |
| 页脚对照图某格是 `no footer ink` | 该页确实没印页码，或页码不在 `--y0/--y1` 区间 | 调 `--y0/--y1` 或 `--min-ink`；若确无页码就靠上下文判断（附件首页/空白背面很常见） |

## 文件结构

```
pdf-interleave_tool_diy/
├── SKILL.md                   # 本文件（技能定义）
├── README.md                  # 面向使用者的说明
├── requirements.txt           # pymupdf / numpy / pillow
└── scripts/
    ├── interleave_pdf.py      # 主脚本（merge / split / verify / info）
    ├── footer_pageno.py       # 合并前的页序判读（页脚页码对照图）
    └── selftest.py            # 44 项自检，含必须失败的反向测试与盲区断言
```

## 实测案例（2026-09-14）

`09_参考资料` 下的伦理批件扫描件被劈成 odd.pdf（9 页）与 even.pdf（9 页）：

```
info   → odd 9 页 / even 9 页，两侧均为 596x841 pt（A4），尺寸 uniform
merge  → 18 页，17.3 MB，verify: checked_pages=18 / mismatches=0 / ALL MATCH
```

随后做往返验证：把成品 split 回 odd/even，再 merge 一次，与原件**逐页位图 md5 比对
零差异**（18/18 页一致，`ROUNDTRIP OK`）。

## 实测案例（2026-09-18）— 两侧页数一样、verify 全绿，但合出来是错的

报批材料扫描件：odd.pdf 7 页、even.pdf 7 页，均 A4、**无文字层**（纯扫描件）。
其中 **odd.pdf 是正面扫描、even.pdf 是反面扫描** —— 后者因此整个是倒序的。

```
info   → 两侧各 7 页，尺寸 uniform   ← 看起来是"标准情况"
merge  → 14 页，verify: mismatches=0 / ALL MATCH   ← 一片绿，但结果是错的
```

`footer_pageno.py` 读出真实印刷页码后才暴露问题：

| 源 | 扫描面 | 各页印的页码 |
|---|---|---|
| odd.pdf | 正面 | 5、6、8、(附件首页无页码)、11、13、15 —— **递增** |
| even.pdf | **反面** | 16、14、12、10、(空白背面)、7、5 —— **递减** |

even.pdf 是**反面扫描**，所以整份倒序（物理必然，见"这个技能解决什么问题"一节）。
且两侧并非互补（odd 含 5、6 连续两页，even 也有一个 5），
实际原稿是页码 5–16 的 12 页材料包，扫描时多出 1 张"劳务服务要求"重号页 + 1 张空白背面。

**一次合对的做法**（用户确认的最终方案）：

```bash
python scripts/interleave_pdf.py merge odd.pdf even.pdf -o merged.pdf --reverse-even --verify
```

输出 14 页，实测页码单调递增 5→16，与"先手工反转 even 再合"的结果**逐页位图 md5 完全一致**。

**教训**：这个案例里 `info` 和 `--verify` 双双给出"没问题"的信号，唯一能发现错误的是
**纸上印的页码**。所以 SOP 里加了 Step 1.5，并把这条盲区钉进了 `selftest.py`。
