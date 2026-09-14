# pdf-interleave_tool_diy

奇偶页 PDF 交叉合并 / 拆分 / 校验工具

把被劈成两半的扫描件还原回正确阅读顺序 —— `odd.pdf`（1,3,5…）+ `even.pdf`（2,4,6…）
→ 一份 1,2,3,4… 的完整 PDF，并逐页证明页序没错。

## 这是什么问题

双面打印后再扫描、或扫描仪开启"奇偶页分离 / 前后页分别输出"时，你会得到两个**各自都不完整**的
PDF：一个只有奇数页，一个只有偶数页。单独打开任一份都是残本，只有交叉合并才有意义。

而合并件一旦串页，比残本更危险 —— 它**看起来是完整的**。所以本工具把「合并」与
「用像素级哈希证明合并正确」做在同一件事里。

## 功能特性

- **交叉合并** — odd/even 按 1,2,3,4… 真实页序重排，输出新文件，原文件零改动
- **不丢页** — 两侧页数不等时，多的尾页原样追加；`--pad blank` 可选补空白页保持奇偶配对
- **页面位图校验** — 72 dpi 渲染取 md5，逐页比对，输出 `ALL MATCH` / `FAILED` 与具体错页
- **反向拆分** — 把一个完整 PDF 拆成 `*_odd.pdf` / `*_even.pdf`（merge 的逆操作）
- **偏移修正** — `--drop-odd N` / `--drop-even N` 处理翻面扫描常见的 ±N 页错位
- **危险操作拦截** — 输出路径等于输入文件、两个输入是同一文件，一律拒绝执行
- **JSON 输出** — `--json` 便于脚本串联，退出码 `0`=一致 / `2`=校验失败 / `1`=参数或IO错误
- **解释器自举** — 用没装 PyMuPDF 的 python 启动也能自动切换解释器跑通

## 安装

```bash
pip install pymupdf
```

无其他依赖（其余全是 Python 标准库）。

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

### 2. 交叉合并 + 校验

```bash
python scripts/interleave_pdf.py merge odd.pdf even.pdf -o merged.pdf --verify
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

### 3. 拆分（需要"先打奇数页再翻面"重新打印时）

```bash
python scripts/interleave_pdf.py split merged.pdf -o ./out --verify
# -> ./out/merged_odd.pdf (1,3,5...)  ./out/merged_even.pdf (2,4,6...)
```

### 4. 只校验一份已有的合并件

```bash
python scripts/interleave_pdf.py verify merged.pdf --odd odd.pdf --even even.pdf
```

## 参数速查

| 子命令 | 关键参数 | 说明 |
|---|---|---|
| `merge` | `ODD EVEN -o OUT` | 交叉合并 |
| | `--first {odd,even}` | 第 1 页取自哪一路（默认 odd）；`merge A B --first even` == `merge B A` |
| | `--drop-odd N` / `--drop-even N` | 跳过源文件开头 N 页，修正 ±N 错位 |
| | `--pad {none,blank}` | 页数不等时补空白页（默认 none，不丢页） |
| | `--verify` / `--no-overwrite` | 合并后校验 / 拒绝覆盖已有文件 |
| `split` | `MERGED -o OUTDIR` | 拆成奇数页/偶数页 |
| | `--prefix odd,even` | 输出文件后缀（默认 odd,even） |
| | `--verify` | 拆分后回拼并与原件比对 |
| `verify` | `MERGED --odd A --even B` | 单独校验页序 |
| `info` | `PDF...` | 只看页数/尺寸/大小，只读 |
| 全局 | `--json` / `--python PATH` | JSON 输出 / 指定解释器（前后位置都能写） |

## 校验原理

每页按 72 dpi 渲染成位图，对 `宽x高|通道数` + 像素数据取 md5；把合并件每一页的哈希，
与"它应该来自的那个源文件的对应页"哈希逐一比对。

比对的是**渲染后的像素**，所以能同时抓住：页序错、内容被替换、页面被旋转或裁切、
页面尺寸被改、以及填充页其实不是空白。任何一页不符即报 `FAILED` 并指出
「第 N 页：期望 odd[7]，实际内容不符」，退出码 `2`。

## 自检

```bash
python scripts/selftest.py     # 27 项断言，全部使用临时生成的合成 PDF
```

覆盖等页合并页序、页数不等不丢页、补空白页、`--first even`、偏移修正、split 往返一致、
**人为错序必须被检出**（防止校验器空转）、危险操作拦截、CLI 参数位置等。

## 实测记录

| 数据 | 输入 | 输出 | 校验 |
|---|---|---|---|
| 伦理批件扫描件 odd/even（A4，596×841 pt） | 9 页 + 9 页 | 18 页 / 17.3 MB | `checked_pages: 18, mismatches: 0, ALL MATCH` |
| 往返测试（成品 → split → merge） | — | 18 页 | 与原件逐页位图 md5 **零差异** |

## 常见问题

**Q：合并后整体错位一页怎么办？**
源文件本身起页不是文档第 1 页（翻面扫描常见）。用 `--drop-odd 1` 或 `--drop-even 1`
去掉多余前导页后重新合并。

**Q：`ALL MATCH` 是否代表内容一定正确？**
不代表。校验证明的是「与源文件一致」，不是「源文件本身分对了」。请人工翻合并件的第 1、2 页，
确认正文（或页脚页码）连得上。

**Q：中文路径报错找不到文件？**
Git Bash 下不要传 `/d/xxx` 这种 UNIX 风格路径给 Python（Windows 不认），统一用
`D:\...` 反斜杠路径，或先 `cd` 到目录再传相对路径。

## 技术要求

- Python 3.8+
- PyMuPDF（`pip install pymupdf`）

## WorkBuddy Skill 集成

本工具同时作为 [WorkBuddy](https://www.codebuddy.cn) Skill 使用（见 `SKILL.md`），
支持自然语言触发："把 odd 和 even 交叉合并"、"奇偶页合并成一个 PDF"、
"把扫描的正反面合成一份"、"校验合并后的页序对不对"。

## License

MIT
