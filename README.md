# pdf-interleave_tool_diy

奇偶页 PDF 交叉合并 / 拆分 / 校验工具

把被劈成两半的扫描件还原回正确阅读顺序 —— `odd.pdf`（1,3,5…）+ `even.pdf`（2,4,6…）
→ 一份 1,2,3,4… 的完整 PDF，并逐页证明页序没错。

> **先读页码再合并。** `info` 页数相等、`verify` 报 `ALL MATCH`，都**不能**证明合对了 ——
> 它们只说明"输出页与来源页一致"，不说明"来源两侧的分页是对的"。本工具因此内置
> `footer_pageno.py`：把每页纸上的**印刷页码**裁出来拼成对照图，一眼看出哪一侧是倒序。

## 这是什么问题

双面打印后再扫描、或扫描仪开启"奇偶页分离 / 前后页分别输出"时，你会得到两个**各自都不完整**的
PDF：一个只有奇数页，一个只有偶数页。单独打开任一份都是残本，只有交叉合并才有意义。

而合并件一旦串页，比残本更危险 —— 它**看起来是完整的**。所以本工具把「合并」与
「用像素级哈希证明合并正确」做在同一件事里，并在合并**之前**提供一道页码判读。

### 反面扫描拿到的一定是倒序（物理必然）

这条要当**规律**用，不是偶发故障：一叠纸正面朝上放进进纸器扫一遍 → 得到正序；
把这叠纸**整摞翻面**再扫一遍，原来压在**最底下**的那张翻到了最上面，于是背面的页序
从**最后一页开始往回走**，扫出来必然是倒序。

以一份 **12 页**双面文档（两面印满）为例：

| 手上这一路是 | 页序 | 典型页码表现 |
|---|---|---|
| 正面扫描 | **正序**（递增） | 1、3、5、7、9、11 |
| **反面扫描** | **倒序**（递减） | 12、10、8、6、4、2 |

> 页码的起始值和步长随原稿而变（原稿从第 5 页起、或中途夹了不编号的附件页，就不会是
> 干净的 1/3/5…）。判据只看**单调方向**：递增=正面，递减=反面。

所以：一路正面 + 一路反面时，**先把反面那一路按倒序处理再合**，不要合完再看结果。
拿不准哪一路是反面，用 `footer_pageno.py` 一读便知 —— 页码递减的就是它。

真实翻车姿势（2026-09-18 实测）：odd 7 页（正面）、even 7 页（**反面**），页数一样、
`verify` 全绿，但 even 页码 16→14→12→10 递减，直接合出来页码是 `5,16,7,14,9,12,…`。
唯一的发现手段就是读印刷页码。

## 功能特性

- **交叉合并** — odd/even 按 1,2,3,4… 真实页序重排，输出新文件，原文件零改动
- **不丢页** — 两侧页数不等时，多的尾页原样追加；`--pad blank` 可选补空白页保持奇偶配对
- **页序判读（合并前）** — `footer_pageno.py` 自动裁切每页页脚、放大页码、拼成对照图，
  纯扫描件（无文字层）同样适用，不需要 OCR
- **倒序还原** — `--reverse-odd` / `--reverse-even` 处理**反面扫描导致的整侧倒序**
- **页面位图校验** — 72 dpi 渲染取 md5，逐页比对，输出 `ALL MATCH` / `FAILED` 与具体错页
- **反向拆分** — 把一个完整 PDF 拆成 `*_odd.pdf` / `*_even.pdf`（merge 的逆操作）
- **偏移修正** — `--drop-odd N` / `--drop-even N` 处理翻面扫描常见的 ±N 页错位
- **危险操作拦截** — 输出路径等于输入文件、两个输入是同一文件，一律拒绝执行
- **JSON 输出** — `--json` 便于脚本串联，退出码 `0`=一致 / `2`=校验失败 / `1`=参数或IO错误
- **解释器自举** — 用没装依赖的 python 启动也能自动切换解释器跑通

## 安装

```bash
pip install -r requirements.txt     # pymupdf + numpy + pillow
```

只跑 `interleave_pdf.py` 的话装 `pymupdf` 就够；`footer_pageno.py` 额外需要
`numpy` + `pillow`。

## 使用方法

### 1. 先看页数

```bash
python scripts/interleave_pdf.py info odd.pdf even.pdf
```

```
command: info
files:
  - {'path': '...\\odd.pdf',  'pages': 9, 'file_size': '10.5 MB', 'page_sizes': {'596.0x841.0': 9}, 'uniform_size': True}
  - {'path': '...\\even.pdf', 'pages': 9, 'file_size': '6.9 MB',  'page_sizes': {'596.0x841.0': 9}, 'uniform_size': True}
```

### 2. 读印刷页码，确认两侧是不是干净的奇偶对（**别跳过**）

```bash
python scripts/footer_pageno.py odd.pdf even.pdf --out ./_footers
```

生成 `odd_footers_1.png` / `even_footers_1.png`（默认每 4 页一张，每格标 `page N`，
页脚数字已自动裁切放大）。照着读一遍：

| 读到的页序 | 做法 |
|---|---|
| 两侧各自递增、页号互补 | 直接合 |
| **一侧递增、另一侧递减** | 递减那侧是**反面扫描**，加 `--reverse-odd` / `--reverse-even` |
| 同一页号出现两次 | 重复扫描页，先决定留哪张 |
| 某页 `no footer ink` | 该页没印页码（附件首页/空白背面常见），靠上下文判断 |
| 页码不互补（断号/重号/对不上） | 不是一份文档的奇偶对，别硬凑，按页码写自定义页序重建 |

### 3. 交叉合并 + 校验

```bash
python scripts/interleave_pdf.py merge odd.pdf even.pdf -o merged.pdf --verify
# 若第 2 步发现某侧是反面扫描（页码递减）：
python scripts/interleave_pdf.py merge odd.pdf even.pdf -o merged.pdf --reverse-even --verify
```

```
command: merge
output: D:\...\merged.pdf
output_size: 17.3 MB
output_pages: 18
odd_pages: 9
even_pages: 9
first: odd
padded_blank_pages: 0
verify:
  checked_pages: 18
  mismatches: 0
  verdict: ALL MATCH
```

### 4. 拆分（需要"先打奇数页再翻面"重新打印时）

```bash
python scripts/interleave_pdf.py split merged.pdf -o ./out --verify
# -> ./out/merged_odd.pdf (1,3,5...)  ./out/merged_even.pdf (2,4,6...)
```

### 5. 只校验一份已有的合并件

```bash
python scripts/interleave_pdf.py verify merged.pdf --odd odd.pdf --even even.pdf
# 若源文件某侧是倒序的，校验时也要带上同样的开关：
python scripts/interleave_pdf.py verify merged.pdf --odd odd.pdf --even even.pdf --reverse-even
```

## 参数速查

| 子命令 | 关键参数 | 说明 |
|---|---|---|
| `merge` | `ODD EVEN -o OUT` | 交叉合并 |
| | `--first {odd,even}` | 第 1 页取自哪一路（默认 odd）；`merge A B --first even` == `merge B A` |
| | `--drop-odd N` / `--drop-even N` | 跳过源文件开头 N 页，修正 ±N 错位 |
| | `--reverse-odd` / `--reverse-even` | 该路整体倒序取页（该路是**反面扫描**时用） |
| | `--pad {none,blank}` | 页数不等时补空白页（默认 none，不丢页） |
| | `--verify` / `--no-overwrite` | 合并后校验 / 拒绝覆盖已有文件 |
| `split` | `MERGED -o OUTDIR` | 拆成奇数页/偶数页 |
| | `--prefix odd,even` | 输出文件后缀（默认 odd,even） |
| | `--verify` | 拆分后回拼并与原件比对 |
| `verify` | `MERGED --odd A --even B` | 单独校验页序（也支持 `--reverse-*` / `--drop-*`） |
| `footer_pageno` | `ODD EVEN [--out DIR]` | 生成页脚页码对照图，只读源文件 |
| | `--zoom` / `--y0` / `--y1` / `--rows` | 放大倍数 / 页脚区间 / 每图页数（默认 4） |
| | `--tile-max-w` / `--min-ink` | 单格宽度上限 / 有墨迹判定阈值 |
| `info` | `PDF...` | 只看页数/尺寸/大小，只读 |
| 全局 | `--json` / `--python PATH` | JSON 输出 / 指定解释器（前后位置都能写） |

> `--drop-*` 与 `--reverse-*` 可叠加，顺序是**先按文件顺序丢开头 N 页，再整体倒序**。

## 校验原理

每页按 72 dpi 渲染成位图，对 `宽x高|通道数` + 像素数据取 md5；把合并件每一页的哈希，
与"它应该来自的那个源文件的对应页"哈希逐一比对。

比对的是**渲染后的像素**，所以能同时抓住：页序错、内容被替换、页面被旋转或裁切、
页面尺寸被改、以及填充页其实不是空白。任何一页不符即报 `FAILED` 并指出
「第 N 页：期望 odd[7]，实际内容不符」，退出码 `2`。

### 它证明不了什么

比对基准是**映射表**（"第 N 页取自 odd[7]"），而映射表是由 `--first / --drop-* /
--reverse-*` 推出来的 —— 源文件本身分错了，映射表就是错的，`verify` 照样报 `ALL MATCH`。
**判定源文件分页是否合理，只能读印刷页码（第 2 步）。**

## 自检

```bash
python scripts/selftest.py     # 44 项断言，全部使用临时生成的合成 PDF
```

覆盖等页合并页序、页数不等不丢页、补空白页、`--first even`、偏移修正、
**`--reverse-*` 整侧倒序还原**、**「倒序侧不倒序时 verify 仍报 ALL MATCH」的盲区断言**、
`--reverse-*` 与 `--drop-*` 叠加、split 往返一致、**人为错序必须被检出**（防止校验器空转）、
危险操作拦截、CLI 参数位置、`footer_pageno` 出图。

## 实测记录

| 日期 | 数据 | 输入 | 输出 | 校验 |
|---|---|---|---|---|
| 2026-09-14 | 伦理批件扫描件（A4，596×841 pt） | 9 页 + 9 页 | 18 页 / 17.3 MB | `checked_pages: 18, mismatches: 0, ALL MATCH` |
| 2026-09-14 | 往返测试（成品 → split → merge） | — | 18 页 | 与原件逐页位图 md5 **零差异** |
| 2026-09-18 | 报批材料扫描件（无文字层；odd 正面 / even **反面**） | 7 页 + 7 页 | 14 页 / 10.5 MB | 直接合 = **乱序**（页码 5,16,7,14,…）；加 `--reverse-even` 后页码单调递增 5→16，与手工反转方案逐页 md5 一致 |

## 常见问题

**Q：合并后整体错位一页怎么办？**
源文件本身起页不是文档第 1 页（翻面扫描常见）。用 `--drop-odd 1` 或 `--drop-even 1`
去掉多余前导页后重新合并。

**Q：合并后页码忽大忽小、整体乱序？**
某一侧是**反面扫描**——整摞纸翻面后页序物理上必然倒置。先用 `footer_pageno.py` 读页码
确认哪一路递减，然后加 `--reverse-odd` / `--reverse-even` 重合并。注意这种情况 `info`
页数相等、`verify` 也会报 `ALL MATCH`，光看输出发现不了。

**Q：`ALL MATCH` 是否代表内容一定正确？**
不代表。校验证明的是「与映射表一致」，不是「源文件本身分对了」。请读一遍印刷页码
（或至少人工翻第 1、2 页），确认页码单调递增。

**Q：中文路径报错找不到文件？**
Git Bash 下不要传 `/d/xxx` 这种 UNIX 风格路径给 Python（Windows 不认），统一用
`D:\...` 反斜杠路径，或先 `cd` 到目录再传相对路径。

**Q：页脚对照图某格显示 `no footer ink`？**
该页确实没印页码（附件首页、空白背面很常见），或页码不在 `--y0/--y1` 默认区间内。
先调 `--y0 0.80 --y1 0.99` 或加大 `--zoom` 再看。

## 技术要求

- Python 3.8+
- `pymupdf`（必需）、`numpy` + `pillow`（仅 `footer_pageno.py` 需要）

## WorkBuddy Skill 集成

本工具同时作为 [WorkBuddy](https://www.codebuddy.cn) Skill 使用（见 `SKILL.md`），
支持自然语言触发："把 odd 和 even 交叉合并"、"奇偶页合并成一个 PDF"、
"even 是倒序的，从后往前抽页合并"、"合并后页码乱了"、"校验合并后的页序对不对"。

## License

MIT
