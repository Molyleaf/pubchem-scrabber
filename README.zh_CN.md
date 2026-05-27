# PubChem 批量自动数据获取客户端 🧪

这是一个为 Windows 操作系统深度优化的企业级 **PubChem 化学数据批量查询与严格对齐导出客户端**。客户端在底层全面融入了官方合规限速保护、智能双轨指数退避重试、多维本地反向缓存以及防丢落盘网关，实现了极高的数据抓取鲁棒性与完美对齐效果。

---

## 🌟 核心特性与架构亮点

* **智能标识符类型推断 (Smart Type Inference)**
  内置智能分类推断引擎，用户只需输入原始化学标识符，程序会自动识别并路由：
  - 纯数字 -> `cid`
  - 以 `InChI=` 开头 -> `inchi`
  - 27位双横线格式（如 `XXXXX-XXXXX-X`） -> `inchikey`
  - 包含常见化学元素的大写字母及配对符号且不含禁用字母 -> `smiles`
  - 其他情况（小写全字母无空格、俗名或商品名） -> `name` (俗名/英文名)
  针对小写纯字母俗名（如 `aspirin`）与简易 SMILES 冲突的问题进行了安全分流优化，100% 避免误判。

* **高健壮网络与双轨重试中枢 (Smart Retry & SSL Monkey Patch)**
  - **代理嗅探**：启动时调用 Windows 系统 API 自动获取全局网络代理（Clash / 系统的 HTTP/HTTPS 代理配置）并自动注入当前 Python 进程。
  - **SSL 穿透**：针对 Python 3.13 下本地代理隧道频发的 `ssl.SSLEOFError` 握手终止故障，内置了全局 SSL 猴子补丁，强制创建不校验的 SSL 协议上下文，实现 100% 代理畅通。
  - **无限指数重试**：针对底层网络连接性错误（超时、连接重置 10054、SSL 握手中断等），采用带有随机抖动（Jitter）的指数退避无限重试轨道，并在重试时打印日志。
  - **5 次 HTTP 重试**：针对 PubChem 服务器超载返回的 503 Server Busy 或 504 Gateway Timeout 错误，重试最多 5 次，失败后自动安全降级为未找到。
  - **API 限速锁**：每次向 PubChem 发送的网络请求间强制引入全局节流锁 `time.sleep(0.25)`，严格遵守每秒不超过 5 次请求的官方合规红线。

* **双核心二级反向缓存 (Double-Core Local Cache)**
  缓存固定持久化在本地的 `cache/pubchem_cache.json`。
  - 以标准的 `InChIKey`（27位哈希）作为全局绝对唯一主键存储化合物详情（`compounds` 详情区）。
  - 使用 `query_index` 二级冗余索引：化合物被获取后，它的 `query`、`cid`、`iupac_name`、`smiles`、`inchi`、`inchikey` 的小写化别名均会被“硬链接”到唯一的 InChIKey。这实现了**一次网络获取，下一次输入任意别名、SMILES 或 ID 都能 100% 瞬时命中本地缓存**。
  - **空值负向缓存 (Negative Caching)**：对于未匹配到或查询失败的输入，在本地缓存标记为 `"404 Not Found"`，避免重复的无效网络连接。
  - **原子级安全落盘**：写入文件时采用临时文件 `.tmp` 写入，完成后 rename 替换原始缓存文件。即便写入过程中断电，也绝对不会损坏原有的缓存 JSON。

* **行级严格对齐与优雅中断 (Strict 100% Row Alignment)**
  - 程序读取输入文件的第一列并提取标识符（支持自动表头剥离）。
  - 输出文件的行数和物理顺序与输入文件 **100% 绝对严格一致**。
  - 当某一行数据在 PubChem 中无匹配或遭遇 404 时，指定的输出字段列统一安全填充为 `"404 Not Found"`，绝不发生物理行错位。
  - **防丢落盘网关**：用户中途按下 `Ctrl+C` 强制中断时，系统会捕获键盘信号，将目前已经成功获取的部分数据对齐写入输出文件，未完成的行填充 `404 Not Found` 后优雅退出，绝不丢失数据。

* **现代富文本 UI 交互 (Rich Aesthetic CLI)**
  使用 `rich` 库构建极具技术感的高品质终端交互，包含高光彩色 Banner 标题、平滑的全局抓取进度条，并在运行结束后打印精美的汇总数据表格。

---

## 🛠 安装指南

我们当前环境已经装好了所有的依赖。如需在新的 Windows 环境中运行，请确保 Python 版本 $\ge$ 3.8，并执行以下命令安装：

```bash
pip install -r requirements.txt
```

### 依赖项列表
* `pubchempy>=1.0.5` (官方 PubChem SDK)
* `pandas>=2.3.3` (高效数据表格处理)
* `openpyxl>=3.1.5` (Excel `.xlsx` 格式支持)
* `rich>=14.2.0` (高品味终端交互 UI)
* `pytest>=9.0.3` (自动化测试框架)

---

## 🚀 运行与命令行参数

您可以通过以下命令运行主程序：

```bash
python app.py --input <输入路径> [--scope <要导出的字段>] [--output <输出路径>] [--batch <批量大小>] [--header <表头策略>]
```

### 参数详解
| 参数名 | 默认值 | 描述 (所有命令行报错均以中文输出) |
| :--- | :--- | :--- |
| `--input` | **必填** | 输入文件的相对或绝对路径，支持 `.csv`、`.xlsx` 和 `.xls` 格式。 |
| `--scope` | `cid name smiles weight` | 需要导出的化合物属性字段列表（空格分隔），可用值见下方映射表。 |
| `--output` | `output.csv` | 输出文件的路径，**缺省不传默认输出到 `output.csv`**。智能根据后缀自动识别格式。 |
| `--batch` | `100` | 批量向网络发起请求的 Chunk 分包大小（仅针对能批量定位的纯数字 CID 生效）。 |
| `--header` | `auto` | 表头策略。`auto`（自动检测首行是否为列标题）、`yes`（强制第一行为标题并跳过）、`no`（无表头第一行即是数据）。 |

### 可用的 Scope 映射列表
| Scope 参数 | 导出列名 | 对应的化合物属性 |
| :--- | :--- | :--- |
| `cid` | `cid` | PubChem 化合物 ID (数字) |
| `name` | `name` | IUPAC 官方国际标准命名 |
| `smiles` | `smiles` | 包含立体信息的异构 SMILES 字符串 |
| `inchi` | `inchi` | 国际化合物标识符标准 InChI |
| `inchikey` | `inchikey` | 27 位 InChIKey 结构哈希值 |
| `weight` | `weight` | 分子量 (g/mol) |
| `formula` | `formula` | 分子式 |
| `xlogp` | `xlogp` | 脂水分配系数 |
| `tpsa` | `tpsa` | 拓扑极性表面积 |
| `charge` | `charge` | 分子总电荷数 |

---

## 💡 使用运行示例

### 1. 缺省极简运行 (缺省输出到项目目录下的 `output.csv`)
```bash
python app.py --input my_compounds.csv
```

### 2. 导出完整属性到 Excel 并采用批量大小 50
```bash
python app.py --input dataset.xlsx --scope cid name smiles weight formula xlogp tpsa --output result.xlsx --batch 50
```

---

## 🧪 自动化测试套件

我们为项目配置了全面的单元测试，完全隔离网络 I/O，使用指数退避的提速 mock 保证在 0.5 秒内疾速跑完！

### 运行全部测试：
```bash
python -m pytest -v
```

---

## 📂 项目模块结构设计说明

为了保持极高的代码维护性与低耦合，核心功能均划分在 `lib/` 目录下：

```
pubchem-scrabber/
│
├── app.py                      # 应用程序的主入口、UI 组装与全局异常拦截
├── requirements.txt            # 项目必需的外部第三方依赖列表
├── README.md                   # 英文版项目使用指南
├── README.zh_CN.md             # 中文版项目使用指南 (本文件)
│
├── lib/                        # 核心服务逻辑文件夹
│   ├── cli_parser.py           # 参数解析、CSV/Excel 健壮加载与表头自动识别
│   ├── network_engine.py       # 代理嗅探注入、SSL穿透补丁与指数重试装饰器
│   ├── cache_manager.py        # 二级多向反向本地缓存、空值缓存与原子落盘
│   └── batch_dispatcher.py     # 整合调度、CID批量/单条分流获取、严格行对齐
│
└── tests/                      # 单元测试文件包
    ├── test_cli_parser.py
    ├── test_network_engine.py
    ├── test_cache_manager.py
    └── test_batch_dispatcher.py
```
