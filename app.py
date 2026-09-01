"""
实习学习 Agent - 本地日报记录与文件管理
启动: python app.py
访问: http://localhost:5000
"""

import os
import re
import json
import requests
from datetime import datetime, date, timedelta
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
import markdown

from doc_parser import extract_text, generate_summary_prompt

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data'
DAILY_DIR = DATA_DIR / 'daily'
DOCS_DIR = DATA_DIR / 'docs'
PROJECTS_DIR = DATA_DIR / 'projects'
REVIEWS_DIR = DATA_DIR / 'reviews'
TOOLS_DIR = DATA_DIR / 'tools'
TAGS_FILE = DATA_DIR / 'tags.json'
MEMORY_FILE = DATA_DIR / 'memory.json'
KNOWLEDGE_FILE = DATA_DIR / 'knowledge.json'
PROJECTS_FILE = DATA_DIR / 'projects.json'
TOOLS_FILE = DATA_DIR / 'tools.json'


def split_tags(raw):
    """切分标签字符串，兼容中英文逗号、分号、顿号"""
    if not raw:
        return []
    return [t.strip() for t in re.split(r'[,，;；、]', raw) if t.strip()]


def load_tags():
    if TAGS_FILE.exists():
        return json.loads(TAGS_FILE.read_text(encoding='utf-8'))
    return {"tags": []}


def save_tags(data):
    TAGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


# ===== 记忆系统 =====

def load_memory():
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text(encoding='utf-8'))
    return None


def save_memory(memory):
    memory['meta']['last_updated'] = date.today().isoformat()
    memory['meta']['total_interactions'] += 1
    MEMORY_FILE.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding='utf-8')


def get_memory_context():
    """生成给 AI 的记忆上下文摘要"""
    memory = load_memory()
    if not memory:
        return ""

    ctx = f"""## 关于这位实习生的记忆档案
- 身份：{memory['profile']['role']}
- 职业目标：{memory['profile']['career_goal']}
"""
    if memory['profile']['strengths']:
        ctx += f"- 已发现的优势：{', '.join(memory['profile']['strengths'])}\n"
    if memory['profile']['weaknesses']:
        ctx += f"- 需要改进的方面：{', '.join(memory['profile']['weaknesses'])}\n"

    # 能力模型
    skills = {k: v for k, v in memory['skill_model'].items() if v > 0}
    if skills:
        ctx += "\n## 当前能力评估\n"
        for skill, level in sorted(skills.items(), key=lambda x: -x[1]):
            ctx += f"- {skill}: {level}/10\n"

    # 最近的建议追踪
    pending_advice = [a for a in memory['advice_tracker'] if a.get('status') == 'pending']
    if pending_advice:
        ctx += "\n## 上次给出的建议（追踪执行情况）\n"
        for a in pending_advice[-5:]:
            ctx += f"- [{a['date']}] {a['advice']}\n"

    # 最近成长记录
    if memory['growth_log']:
        ctx += "\n## 近期成长轨迹\n"
        for g in memory['growth_log'][-5:]:
            ctx += f"- [{g['date']}] {g['summary']}"
            if g.get('scores'):
                ctx += f" (充实度{g['scores']['fullness']}/成长度{g['scores']['growth']})"
            ctx += "\n"

    # 里程碑
    if memory['milestones']:
        ctx += "\n## 已达成的里程碑\n"
        for m in memory['milestones']:
            ctx += f"- [{m['date']}] {m['content']}\n"

    return ctx


def update_memory_from_review(review_content, scores, tags, week_start):
    """从复盘结果中更新记忆"""
    memory = load_memory()
    if not memory:
        return

    # 记录成长日志
    memory['growth_log'].append({
        'date': week_start,
        'summary': review_content[:200].replace('\n', ' '),
        'scores': scores,
        'tags': tags,
    })

    # 更新能力模型：有相关标签的技能 +0.5
    tag_skill_map = {
        '数据分析': ['数据分析', 'SQL', '数据', '报表', '分析'],
        '用户运营': ['用户运营', '用户', '活跃', '留存', '召回'],
        '策略思维': ['策略', '方案', '规划', '竞品', 'AB测试'],
        '产品感觉': ['产品', '需求', '功能', '体验', 'PRD'],
        '文案撰写': ['文案', '内容', '推文', '文章', '写作'],
        '项目管理': ['项目', '排期', '进度', '协调', '汇报'],
        '沟通协作': ['沟通', '会议', '对齐', '协作', '跨部门'],
        '工具使用': ['工具', 'Excel', 'Python', 'SQL', '效率'],
    }
    for skill, keywords in tag_skill_map.items():
        for tag in tags:
            if any(kw in tag for kw in keywords):
                memory['skill_model'][skill] = min(10, memory['skill_model'].get(skill, 0) + 0.5)
                break

    save_memory(memory)


def update_memory_advice(advices, week_start):
    """记录 AI 给出的新建议"""
    memory = load_memory()
    if not memory:
        return

    # 将旧的 pending 建议标记为 expired（超过2周未跟进）
    for a in memory['advice_tracker']:
        if a.get('status') == 'pending':
            if week_start > a.get('date', ''):
                a['status'] = 'expired'

    # 添加新建议
    for advice in advices:
        memory['advice_tracker'].append({
            'date': week_start,
            'advice': advice,
            'status': 'pending',
        })

    save_memory(memory)


# ===== 知识库 =====

def load_knowledge():
    if KNOWLEDGE_FILE.exists():
        return json.loads(KNOWLEDGE_FILE.read_text(encoding='utf-8'))
    return {"documents": []}


def save_knowledge(data):
    KNOWLEDGE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def get_knowledge_context():
    """生成给 AI 的知识库上下文摘要"""
    knowledge = load_knowledge()
    if not knowledge['documents']:
        return ""

    ctx = "\n## 已学习的文档知识库\n"
    for doc in knowledge['documents'][-15:]:  # 最近15份
        ctx += f"- 【{doc.get('category', '未分类')}】{doc['title']}: {doc['one_line_summary']}\n"
        if doc.get('key_points'):
            for point in doc['key_points'][:2]:
                ctx += f"  - {point}\n"
    return ctx


def process_uploaded_file(filepath):
    """解析上传的文件并生成 AI 摘要，加入知识库"""
    text, meta = extract_text(filepath)
    if not text:
        return None

    # 调用 AI 生成摘要
    prompt = generate_summary_prompt(text, filepath.name)
    system = "你是一个知识管理助手，负责对文档进行分类和摘要。只输出 JSON，不要加任何多余内容。不要输出思考过程。"
    result = call_llm(prompt, system=system)

    # 解析 AI 返回的 JSON（兼容 <think> 标签和各种代码块格式）
    try:
        import re
        clean = result.strip()
        # 去除部分模型输出的 <think>...</think> 思考过程
        clean = re.sub(r'<think>.*?</think>', '', clean, flags=re.DOTALL).strip()
        # 去除 markdown 代码块
        if '```' in clean:
            code_match = re.search(r'```(?:json)?\s*\n?(.*?)```', clean, re.DOTALL)
            if code_match:
                clean = code_match.group(1).strip()
        # 尝试找到 JSON 对象
        if not clean.startswith('{'):
            json_match = re.search(r'\{.*\}', clean, re.DOTALL)
            if json_match:
                clean = json_match.group(0)
        summary = json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        summary = {
            'title': filepath.stem,
            'category': '其他',
            'key_points': [],
            'keywords': [],
            'one_line_summary': '解析失败，请手动补充',
            'relevance_to_ops': '',
        }

    # 加入知识库
    knowledge = load_knowledge()
    doc_entry = {
        **summary,
        'filename': filepath.name,
        'format': filepath.suffix.lower(),
        'added_date': date.today().isoformat(),
        'text_preview': text[:500],
    }
    # 避免重复
    knowledge['documents'] = [d for d in knowledge['documents'] if d['filename'] != filepath.name]
    knowledge['documents'].append(doc_entry)
    save_knowledge(knowledge)

    return doc_entry


# ===== 项目作品集 =====

def load_projects():
    if PROJECTS_FILE.exists():
        return json.loads(PROJECTS_FILE.read_text(encoding='utf-8'))
    return {"projects": []}


def save_projects(data):
    PROJECTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def process_project_file(filepath):
    """解析项目文档并用 AI 提取项目信息"""
    text, meta = extract_text(filepath)
    if not text:
        return None

    # 项目专用 AI prompt
    prompt = f"""请从以下项目文档中提取关键信息，以 JSON 格式返回。

背景信息：文档作者是一名策略运营/产品运营实习生，请基于此身份判断其在项目中的角色。

文档内容（前4000字）：
{text[:4000]}

请返回以下 JSON 格式（只输出 JSON，不要加任何其他内容）：
{{
    "project_name": "项目名称",
    "time_period": "起止时间，精确到月份即可，如 2026-06。如果文档中没有明确时间信息，填写当前月份",
    "role": "在项目中承担的具体职责（描述做了什么，而不是岗位头衔。如'负责数据分析与报表自动化'而不是'数据开发工程师'）",
    "description": "一句话描述项目做了什么",
    "achievements": ["成果1（动词开头）", "成果2", "成果3"],
    "metrics": ["量化指标1", "量化指标2"],
    "skills": ["技能1", "技能2", "技能3"],
    "ai_insights": "这个项目对职业发展的价值（1-2句话）"
}}

提取要求：
- project_name: 提取项目的正式名称
- achievements: 3-5 条核心成果，每条以动词开头（如"搭建了…""优化了…""推动了…"）
- metrics: 尽量提取可量化的数据指标（如用户量、效率提升百分比、时间节省等）
- skills: 从以下技能中选择相关的：数据分析、SQL、Python、用户运营、策略思维、产品设计、项目管理、文案撰写、沟通协作、工具使用
- ai_insights: 站在 HR 视角，点评这个项目经验的亮点和对求职的加分点"""

    system = "你是一位资深的 HR 顾问和职业发展教练。你擅长从项目文档中提炼出最有价值的职业经历描述。只输出 JSON，不要加任何多余内容。不要输出思考过程。"
    result = call_llm(prompt, system=system)
    print(f"[DEBUG] process_project_file LLM result (first 500 chars): {result[:500]}")

    # 如果 AI 调用本身失败，直接返回带错误信息的 fallback
    if result.startswith('AI 调用失败'):
        print(f"[ERROR] LLM call failed: {result}")
        project_info = {
            'project_name': filepath.stem,
            'time_period': '',
            'role': '',
            'description': f'AI 解析失败: {result}',
            'achievements': [],
            'metrics': [],
            'skills': [],
            'ai_insights': '',
        }
    else:
        # 解析 AI 返回的 JSON（兼容 <think> 标签和各种代码块格式）
        try:
            clean = result.strip()
            import re
            clean = re.sub(r'<think>.*?</think>', '', clean, flags=re.DOTALL).strip()
            if '```' in clean:
                code_match = re.search(r'```(?:json)?\s*\n?(.*?)```', clean, re.DOTALL)
                if code_match:
                    clean = code_match.group(1).strip()
            if not clean.startswith('{'):
                json_match = re.search(r'\{.*\}', clean, re.DOTALL)
                if json_match:
                    clean = json_match.group(0)
            project_info = json.loads(clean)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[ERROR] JSON parse failed: {e}")
            print(f"[ERROR] Cleaned content: {clean[:300]}")
            project_info = {
                'project_name': filepath.stem,
                'time_period': '',
                'role': '',
                'description': '解析失败，请手动补充',
                'achievements': [],
                'metrics': [],
                'skills': [],
                'ai_insights': '',
            }

    # 生成唯一 ID
    projects = load_projects()
    today_str = date.today().strftime('%Y%m%d')
    idx = len([p for p in projects['projects'] if today_str in p.get('id', '')]) + 1
    project_id = f"proj_{today_str}_{idx:03d}"

    # 构建完整条目
    project_entry = {
        'id': project_id,
        **project_info,
        'filename': filepath.name,
        'format': filepath.suffix.lower(),
        'added_date': date.today().isoformat(),
        'text_preview': text[:500],
    }

    # 避免重复（同文件名覆盖）
    projects['projects'] = [p for p in projects['projects'] if p['filename'] != filepath.name]
    projects['projects'].append(project_entry)
    save_projects(projects)

    return project_entry


def get_projects_context():
    """生成给 AI 的项目经历上下文"""
    projects = load_projects()
    if not projects['projects']:
        return ""

    ctx = "\n## 已完成的项目经历\n"
    for p in projects['projects']:
        ctx += f"\n### {p['project_name']}"
        if p.get('time_period'):
            ctx += f"（{p['time_period']}）"
        ctx += f"\n- 角色：{p.get('role', '未知')}\n"
        if p.get('achievements'):
            ctx += "- 核心成果：\n"
            for a in p['achievements']:
                ctx += f"  - {a}\n"
        if p.get('metrics'):
            ctx += f"- 量化指标：{', '.join(p['metrics'])}\n"
        if p.get('skills'):
            ctx += f"- 技能标签：{', '.join(p['skills'])}\n"
    return ctx


def parse_frontmatter(content):
    """解析 YAML 风格 frontmatter，返回 (meta_dict, body)。
    容错：缺少闭合 --- 或格式异常时不抛异常，整体当正文处理。"""
    meta = {}
    body = content
    lines = content.split('\n')
    if lines and lines[0].strip() == '---':
        end_idx = content.find('---', 4)
        if end_idx != -1:
            header = content[4:end_idx]
            body = content[end_idx + 3:].strip()
            for line in header.strip().split('\n'):
                if ':' in line:
                    k, v = line.split(':', 1)
                    meta[k.strip()] = v.strip()
    return meta, body


def format_cn_date(iso_str):
    """2026-06-22 → 2026年6月22日；解析失败则原样返回"""
    try:
        y, m, d = iso_str.split('-')
        return f"{int(y)}年{int(m)}月{int(d)}日"
    except (ValueError, AttributeError):
        return iso_str


def format_date_range(start, end=''):
    """生成中文日期显示。跨天时显示 起始 - 结束"""
    start_cn = format_cn_date(start)
    if end and end != start:
        return f"{start_cn} - {format_cn_date(end)}"
    return start_cn


# ===== 小工具箱 =====

def load_tools():
    if TOOLS_FILE.exists():
        return json.loads(TOOLS_FILE.read_text(encoding='utf-8'))
    return {"tools": []}


def save_tools(data):
    TOOLS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def extract_zip_readme(filepath):
    """从 zip 中提取 README（README.md / README.txt / readme 等），返回文本或空串"""
    import zipfile
    try:
        with zipfile.ZipFile(filepath) as zf:
            # 找到路径最浅的 readme 文件
            candidates = []
            for name in zf.namelist():
                base = name.split('/')[-1].lower()
                if base.startswith('readme'):
                    depth = name.count('/')
                    candidates.append((depth, name))
            if not candidates:
                return ''
            candidates.sort()
            target = candidates[0][1]
            with zf.open(target) as fp:
                raw = fp.read()
            for enc in ('utf-8', 'gbk', 'latin-1'):
                try:
                    return raw.decode(enc).strip()
                except UnicodeDecodeError:
                    continue
            return ''
    except (zipfile.BadZipFile, OSError):
        return ''


def process_tool_zip(filepath, name='', description=''):
    """处理上传的工具 zip：记录元信息，自动读取 README 作为描述"""
    import zipfile

    readme = extract_zip_readme(filepath)
    # 描述优先级：用户手填 > README 首段 > 空
    desc = description.strip()
    if not desc and readme:
        # 取 README 第一个非空段落作为简介
        for para in readme.split('\n\n'):
            cleaned = para.strip().lstrip('#').strip()
            if cleaned:
                desc = cleaned[:200]
                break

    # 列出 zip 内文件，方便预览内容
    file_list = []
    try:
        with zipfile.ZipFile(filepath) as zf:
            file_list = [n for n in zf.namelist() if not n.endswith('/')][:30]
    except (zipfile.BadZipFile, OSError):
        pass

    tools = load_tools()
    today_str = date.today().strftime('%Y%m%d')
    idx = len([t for t in tools['tools'] if today_str in t.get('id', '')]) + 1
    tool_id = f"tool_{today_str}_{idx:03d}"

    tool_entry = {
        'id': tool_id,
        'name': name.strip() or filepath.stem,
        'description': desc,
        'readme': readme[:2000],
        'file_list': file_list,
        'filename': filepath.name,
        'size': filepath.stat().st_size,
        'added_date': date.today().isoformat(),
    }
    # 同文件名覆盖
    tools['tools'] = [t for t in tools['tools'] if t['filename'] != filepath.name]
    tools['tools'].append(tool_entry)
    save_tools(tools)
    return tool_entry


def get_all_dailies():
    """获取所有日报，按日期倒序"""
    dailies = []
    for f in sorted(DAILY_DIR.glob('*.md'), reverse=True):
        try:
            content = f.read_text(encoding='utf-8')
            meta, body = parse_frontmatter(content)
        except Exception as e:
            print(f"[WARN] 解析日报失败 {f.name}: {e}")
            continue
        dailies.append({
            'date': f.stem,
            'date_end': meta.get('date_end', ''),
            'date_display': format_date_range(f.stem, meta.get('date_end', '')),
            'title': meta.get('title', f.stem),
            'tags': split_tags(meta.get('tags', '')),
            'body': body,
            'html': markdown.markdown(body, extensions=['tables', 'fenced_code']),
        })
    return dailies


def get_all_docs():
    """获取所有学习文件"""
    docs = []
    for f in sorted(DOCS_DIR.iterdir()):
        if f.name == '.gitkeep':
            continue
        docs.append({
            'name': f.name,
            'size': f.stat().st_size,
            'modified': datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d'),
            'is_md': f.suffix == '.md',
        })
    return docs


# ===== AI 辅助 =====

CONFIG_FILE = BASE_DIR / 'config.json'


def load_config():
    """读取 LLM 配置。优先级：环境变量 > config.json。
    环境变量：LLM_BASE_URL / LLM_API_KEY / LLM_MODEL"""
    config = {}
    if CONFIG_FILE.exists():
        config = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))

    config['base_url'] = os.environ.get('LLM_BASE_URL', config.get('base_url'))
    config['api_key'] = os.environ.get('LLM_API_KEY', config.get('api_key'))
    config['model'] = os.environ.get('LLM_MODEL', config.get('model'))

    if not config.get('base_url') or not config.get('api_key') or not config.get('model'):
        return None
    return config


def call_llm(prompt, system="你是一个实习生的工作助手，帮助整理和分析工作内容。", timeout=120):
    """调用 LLM API（OpenAI 兼容格式）"""
    config = load_config()
    if not config:
        return "错误：未找到 config.json，请配置 API 信息"

    try:
        resp = requests.post(
            f"{config['base_url']}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": config['model'],
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"AI 调用失败: {str(e)}"


# ===== 路由 =====

@app.route('/')
def index():
    dailies = get_all_dailies()
    docs = get_all_docs()
    return render_template('index.html', dailies=dailies, docs=docs, today=date.today().isoformat())


@app.route('/daily/new', methods=['GET', 'POST'])
def daily_new():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        tags = request.form.get('tags', '').strip()
        content = request.form.get('content', '').strip()
        date_str = request.form.get('date', date.today().isoformat())
        date_end = request.form.get('date_end', '').strip()

        # 生成 markdown 文件
        frontmatter = f"title: {title}\ntags: {tags}\ndate: {date_str}"
        if date_end and date_end != date_str:
            frontmatter += f"\ndate_end: {date_end}"

        md_content = f"""---
{frontmatter}
---

{content}
"""
        filepath = DAILY_DIR / f"{date_str}.md"
        filepath.write_text(md_content, encoding='utf-8')

        # 更新标签索引
        tag_data = load_tags()
        for t in split_tags(tags):
            if t not in tag_data['tags']:
                tag_data['tags'].append(t)
        save_tags(tag_data)

        return redirect(url_for('index'))

    tag_data = load_tags()
    return render_template('daily.html', tags=tag_data['tags'], today=date.today().isoformat())


@app.route('/daily/<date_str>')
def daily_view(date_str):
    filepath = DAILY_DIR / f"{date_str}.md"
    if not filepath.exists():
        return "日报不存在", 404
    content = filepath.read_text(encoding='utf-8')
    meta, body = parse_frontmatter(content)
    html = markdown.markdown(body, extensions=['tables', 'fenced_code'])
    title = meta.get('title', date_str)
    date_display = format_date_range(date_str, meta.get('date_end', ''))
    return render_template('daily_view.html', date=date_display, title=title, html=html)


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        files = request.files.getlist('files')
        results = []
        for f in files:
            if f.filename:
                safe_name = f.filename.replace('\\', '/').split('/')[-1]
                save_path = DOCS_DIR / safe_name
                f.save(save_path)
                # 自动解析并生成摘要
                doc_entry = process_uploaded_file(save_path)
                if doc_entry:
                    results.append(doc_entry)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'results': results})
        return redirect(url_for('index'))
    knowledge = load_knowledge()
    return render_template('upload.html', knowledge=knowledge['documents'])


@app.route('/docs/<filename>')
def serve_doc(filename):
    return send_from_directory(DOCS_DIR, filename)


@app.route('/projects', methods=['GET', 'POST'])
def projects():
    """项目作品集页面"""
    if request.method == 'POST':
        files = request.files.getlist('files')
        results = []
        for f in files:
            if f.filename:
                safe_name = f.filename.replace('\\', '/').split('/')[-1]
                save_path = PROJECTS_DIR / safe_name
                f.save(save_path)
                # 解析项目文档
                project_entry = process_project_file(save_path)
                if project_entry:
                    results.append(project_entry)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'results': results})
        return redirect(url_for('projects'))
    project_data = load_projects()
    return render_template('projects.html', projects=project_data['projects'])


@app.route('/projects/<filename>')
def serve_project_file(filename):
    return send_from_directory(PROJECTS_DIR, filename)


@app.route('/api/projects/delete', methods=['POST'])
def delete_project():
    """删除一个项目记录"""
    data = request.get_json()
    project_id = data.get('id', '')

    projects = load_projects()
    # 找到要删除的项目
    target = None
    for p in projects['projects']:
        if p['id'] == project_id:
            target = p
            break

    if not target:
        return jsonify({'success': False, 'error': '项目不存在'})

    # 删除文件
    file_path = PROJECTS_DIR / target['filename']
    if file_path.exists():
        file_path.unlink()

    # 从列表中移除
    projects['projects'] = [p for p in projects['projects'] if p['id'] != project_id]
    save_projects(projects)

    return jsonify({'success': True})


@app.route('/tools', methods=['GET', 'POST'])
def tools():
    """小工具箱：上传/展示自己做的小工具（zip）"""
    if request.method == 'POST':
        files = request.files.getlist('files')
        name = request.form.get('name', '')
        description = request.form.get('description', '')
        results = []
        for f in files:
            if not f.filename:
                continue
            safe_name = f.filename.replace('\\', '/').split('/')[-1]
            if not safe_name.lower().endswith('.zip'):
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'error': f'{safe_name} 不是 zip 文件'})
                continue
            save_path = TOOLS_DIR / safe_name
            f.save(save_path)
            tool_entry = process_tool_zip(save_path, name=name, description=description)
            if tool_entry:
                results.append(tool_entry)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'results': results})
        return redirect(url_for('tools'))
    tool_data = load_tools()
    return render_template('tools.html', tools=tool_data['tools'])


@app.route('/tools/<filename>')
def serve_tool_file(filename):
    return send_from_directory(TOOLS_DIR, filename, as_attachment=True)


@app.route('/api/tools/delete', methods=['POST'])
def delete_tool():
    """删除一个工具记录及其文件"""
    data = request.get_json()
    tool_id = data.get('id', '')

    tools = load_tools()
    target = next((t for t in tools['tools'] if t['id'] == tool_id), None)
    if not target:
        return jsonify({'success': False, 'error': '工具不存在'})

    file_path = TOOLS_DIR / target['filename']
    if file_path.exists():
        file_path.unlink()

    tools['tools'] = [t for t in tools['tools'] if t['id'] != tool_id]
    save_tools(tools)
    return jsonify({'success': True})


@app.route('/api/stats')
def api_stats():
    """API: 统计数据"""
    dailies = get_all_dailies()
    docs = get_all_docs()
    all_tags = {}
    for d in dailies:
        for t in d['tags']:
            all_tags[t] = all_tags.get(t, 0) + 1
    return jsonify({
        'total_days': len(dailies),
        'total_docs': len(docs),
        'tags': all_tags,
        'dates': [d['date'] for d in dailies],
    })


@app.route('/api/ai-assist', methods=['POST'])
def ai_assist():
    """AI 辅助写日报：带记忆和知识库上下文"""
    data = request.get_json()
    notes = data.get('notes', '').strip()
    if not notes:
        return jsonify({'error': '请输入今日工作要点'}), 400

    memory_ctx = get_memory_context()
    knowledge_ctx = get_knowledge_context()

    prompt = f"""请帮我把以下工作要点整理成一份结构化的实习日报（Markdown 格式）。
要求：
1. 分为「今日工作」「学习收获」「遇到的问题」「明日计划」四个部分
2. 如果某个部分要点里没提到，可以留空或写"无"
3. 语言简洁专业，保持原意不要过度发挥
4. 直接输出 Markdown 内容，不要加额外解释
5. 如果今天的工作和之前给出的建议相关，在「学习收获」里简要提及进步
6. **如果工作内容和知识库里的文档相关，在「学习收获」里关联，比如"应用了XX文档里学到的XX方法论"**

我的工作要点：
{notes}"""

    system = f"""你是一个实习生的专属成长导师，帮助整理和分析工作内容。你了解这位实习生的背景和成长历程，也了解她学习过的知识。

{memory_ctx}

{knowledge_ctx}"""

    result = call_llm(prompt, system=system)
    return jsonify({'content': result})


@app.route('/review')
def weekly_review():
    """每周 AI 复盘页面，附带历史复盘列表"""
    reviews = []
    for f in sorted(REVIEWS_DIR.glob('*.json'), reverse=True):
        if f.name == '.gitkeep':
            continue
        review = json.loads(f.read_text(encoding='utf-8'))
        # 排除无效复盘
        if review.get('scores', {}).get('fullness', 0) == 0 and review.get('scores', {}).get('growth', 0) == 0:
            continue
        if review.get('content', '').startswith('AI 调用失败'):
            continue
        reviews.append(review)
    return render_template('review.html', reviews=reviews)


@app.route('/api/review', methods=['POST'])
def api_review():
    """生成 AI 周复盘分析，带记忆上下文，并自动更新记忆"""
    import re
    data = request.get_json()
    weeks_ago = data.get('weeks_ago', 0)  # 0=本周, 1=上周
    force = data.get('force', False)  # 强制重新生成

    # 计算目标周的日期范围
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday() + 7 * weeks_ago)
    end_of_week = start_of_week + timedelta(days=6)

    # 如果已有保存的复盘且不是强制重新生成，直接返回
    review_file = REVIEWS_DIR / f"{start_of_week.isoformat()}.json"
    if review_file.exists() and not force:
        saved = json.loads(review_file.read_text(encoding='utf-8'))
        # 校验缓存有效性：跳过失败的复盘
        is_valid = True
        if saved.get('scores', {}).get('fullness', 0) == 0 and saved.get('scores', {}).get('growth', 0) == 0:
            is_valid = False
        if saved.get('content', '').startswith('AI 调用失败'):
            is_valid = False
        if is_valid:
            return jsonify(saved)
        # 无效缓存 → 跳过，继续重新生成

    # 收集该周的日报（支持跨天日报：日期范围与目标周有重叠即纳入）
    dailies = get_all_dailies()
    week_start_str = start_of_week.isoformat()
    week_end_str = end_of_week.isoformat()
    week_dailies = []
    for d in dailies:
        d_start = d['date']
        d_end = d.get('date_end') or d_start
        # 两个区间有重叠：日报结束 >= 周开始 且 日报开始 <= 周结束
        if d_end >= week_start_str and d_start <= week_end_str:
            week_dailies.append(d)

    if not week_dailies:
        return jsonify({'error': f'{start_of_week} ~ {end_of_week} 这周没有日报记录'}), 400

    # 拼接日报内容
    content_summary = ""
    for d in sorted(week_dailies, key=lambda x: x['date']):
        content_summary += f"\n### {d['date']} - {d['title']}\n{d['body']}\n"

    # 获取记忆上下文
    memory_ctx = get_memory_context()
    knowledge_ctx = get_knowledge_context()
    projects_ctx = get_projects_context()

    prompt = f"""请对以下一周的实习日报进行复盘分析。

{content_summary}

请从以下维度分析（Markdown 格式输出）：
## 本周总结
简要概括这周做了什么（3-5句话）

## 能力成长
分析这周在哪些技能上有提升，具体体现在哪里。如果和之前的建议相关，指出"上次建议XX，本周在这方面有所行动/尚未改善"。
**如果本周学习或应用了知识库中的文档，请明确指出。**

## 发现的问题
这周工作中暴露出哪些不足或瓶颈。如果是反复出现的问题，请直接指出。

## 与目标的距离
基于职业目标（策略运营/产品运营），分析本周的工作对目标的贡献度，哪些经验可以写进简历。

## 下周建议
给出3条具体、可执行的建议（不要空泛的"多学习"，要具体到"本周尝试用SQL完成一次用户分群分析"这种级别）

## 成长评分
给本周的工作充实度和成长度各打一个分（1-10分），并简要说明理由。
请在最后单独一行输出格式：[评分:充实度X/成长度Y]，例如 [评分:充实度7/成长度6]
再另起一行输出3条建议摘要：[建议:建议1|建议2|建议3]"""

    system = f"""你是一位资深的策略运营总监，同时也是这位实习生的专属成长导师。
你了解她的全部成长历程，你的分析要基于历史数据，发现趋势和规律。
你也了解她学习过的所有文档，能够关联工作实践和知识积累。
你还了解她参与过的所有项目，能够将日常工作与项目经历联系起来分析。
你要像一个严格但关心学生的导师：直指问题，但也肯定进步。
不要泛泛而谈，要具体、有洞察力、可执行。

{memory_ctx}

{knowledge_ctx}

{projects_ctx}"""

    result = call_llm(prompt, system=system, timeout=180)

    # 解析评分
    scores = {'fullness': 0, 'growth': 0}
    score_match = re.search(r'\[评分:充实度(\d+)/成长度(\d+)\]', result)
    if score_match:
        scores['fullness'] = int(score_match.group(1))
        scores['growth'] = int(score_match.group(2))

    # 解析建议
    advices = []
    advice_match = re.search(r'\[建议:(.+?)\]', result)
    if advice_match:
        advices = [a.strip() for a in advice_match.group(1).split('|') if a.strip()]

    # 保存复盘结果
    week_tags = list(set(t for d in week_dailies for t in d['tags']))
    review_data = {
        'content': result,
        'date_range': f"{start_of_week.isoformat()} ~ {end_of_week.isoformat()}",
        'week_start': start_of_week.isoformat(),
        'daily_count': len(week_dailies),
        'scores': scores,
        'generated_at': datetime.now().isoformat(),
        'tags': week_tags,
    }
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    review_file.write_text(json.dumps(review_data, ensure_ascii=False, indent=2), encoding='utf-8')

    # 更新记忆系统
    update_memory_from_review(result, scores, week_tags, start_of_week.isoformat())
    if advices:
        update_memory_advice(advices, start_of_week.isoformat())

    return jsonify(review_data)


@app.route('/dashboard')
def dashboard():
    """阶段看板：展示所有历史复盘和成长趋势"""
    reviews = []
    for f in sorted(REVIEWS_DIR.glob('*.json')):
        if f.name == '.gitkeep':
            continue
        review = json.loads(f.read_text(encoding='utf-8'))
        reviews.append(review)
    return render_template('dashboard.html', reviews=reviews)


if __name__ == '__main__':
    # 确保目录存在
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    print("[OK] 实习学习 Agent 已启动")
    print("     访问 http://localhost:5000")
    # debug 默认关闭；本地开发可设 FLASK_DEBUG=1 开启（注意调试器可远程执行代码，勿暴露到公网）
    debug_mode = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    app.run(debug=debug_mode, port=5000)
