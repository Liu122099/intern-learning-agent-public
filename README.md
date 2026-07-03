# 成长记录 Agent

一个带长期记忆的个人成长 Agent。每天写日报、上传学到的文档和做过的项目，它会用 AI 帮你复盘、追踪能力成长、把零散的工作沉淀成可用的简历素材。越用越懂你。

适合实习生、职场新人，或任何想系统化记录和复盘自己成长的人。纯本地运行，数据都是你自己的文件。

## 特性

- 📝 **写日报** —— Markdown 格式，支持标签和跨天日报
- 🤖 **AI 辅助** —— 丢几个要点，AI 结合你的历史记忆整理成结构化日报
- 📚 **知识库** —— 上传文档（PDF/Word/PPT/Markdown），AI 自动分类、摘要
- 📂 **项目作品集** —— 上传项目文档，AI 提取成果/指标/技能，沉淀简历素材
- 🧰 **小工具箱** —— 上传自己做的工具（zip），自动读取 README 作为说明
- 🔄 **周复盘** —— AI 读整周日报做复盘，打成长分、给可执行建议，并写回记忆
- 📊 **成长看板** —— 可视化历史复盘和成长趋势
- 📄 **一键报告** —— 生成自包含的 HTML 成长报告

## 核心亮点：记忆闭环

这是它和普通日报工具的区别 —— 它会「记住」并「进化」：

```
写日报  →  周复盘 AI 分析  →  自动更新 memory.json
  ↑                                      │
  └──── 下次 AI 把记忆作为上下文喂回 ──────┘
```

`data/memory.json` 累积你的画像、能力模型评分、AI 给过的建议（带执行追踪）、成长日志。每次 AI 分析都基于这些历史数据，所以它对你的了解是逐周累加的。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 AI 接口（复制示例并填入你的信息）
cp config.example.json config.json
# 然后编辑 config.json 填入你的 LLM 接口地址、key、模型名

# 3. 启动
python app.py
```

打开浏览器访问 http://localhost:5000

## 配置 AI

AI 功能需要一个 **OpenAI 兼容**的 LLM 接口（如 OpenAI、DeepSeek、通义千问、本地 Ollama 等）。两种配置方式，**环境变量优先级高于 config.json**：

方式一 —— `config.json`（已被 .gitignore，不会提交）：

```json
{
  "base_url": "https://your-llm-endpoint.com",
  "api_key": "your-api-key",
  "model": "your-model-name"
}
```

方式二 —— 环境变量：

```bash
export LLM_BASE_URL="https://your-llm-endpoint.com"
export LLM_API_KEY="your-api-key"
export LLM_MODEL="your-model-name"
```

接口按 `{base_url}/v1/chat/completions` 调用。没配置时网页能正常打开，但 AI 功能会返回提示。

## 生成成长报告

```bash
python generate_report.py
# → output/report.html（自包含单文件，可直接分享或打印）
```

## 数据存储

无数据库，全部是 `data/` 下的纯文件，方便备份和 git 版本管理：

```
data/
├── daily/{YYYY-MM-DD}.md   # 日报
├── docs/                   # 知识库原始文档
├── projects/               # 项目原始文档
├── tools/                  # 小工具 zip 包
├── reviews/{周一日期}.json  # 每周复盘结果
├── memory.json             # 记忆档案（画像/能力/建议/成长日志）
├── knowledge.json          # 知识库索引（AI 摘要）
├── projects.json           # 项目作品集索引
├── tools.json              # 小工具箱索引
└── tags.json               # 标签索引
```

仓库自带一篇示例日报（`data/daily/2024-01-15.md`），删掉它就是干净的空环境。

## 项目结构

```
├── app.py                 # Flask 主程序（路由 + 记忆/知识库/项目/复盘逻辑）
├── doc_parser.py          # 文档解析（PDF/Word/PPT/Markdown 提取文本）
├── generate_report.py     # 静态成长报告生成
├── config.example.json    # AI 配置示例（复制为 config.json 使用）
├── requirements.txt
├── templates/             # 网页模板（Jinja2）
├── data/                  # 所有数据
└── output/                # 生成的报告
```

## 技术栈

- Python + Flask
- 纯文件存储，无数据库
- OpenAI 兼容的 LLM 接口
- 文档解析：pdfplumber / python-docx / python-pptx

## License

MIT
