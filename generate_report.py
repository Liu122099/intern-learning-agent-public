"""
一键生成实习成长报告
用法: python generate_report.py
输出: output/report.html
"""

import json
import re
from pathlib import Path
from datetime import datetime

import markdown

BASE_DIR = Path(__file__).parent
DAILY_DIR = BASE_DIR / 'data' / 'daily'
DOCS_DIR = BASE_DIR / 'data' / 'docs'
PROJECTS_FILE = BASE_DIR / 'data' / 'projects.json'
OUTPUT_DIR = BASE_DIR / 'output'


def format_cn_date(iso_str):
    try:
        y, m, d = iso_str.split('-')
        return f"{int(y)}年{int(m)}月{int(d)}日"
    except (ValueError, AttributeError):
        return iso_str


def format_date_range(start, end=''):
    start_cn = format_cn_date(start)
    if end and end != start:
        return f"{start_cn} - {format_cn_date(end)}"
    return start_cn


def parse_daily(filepath):
    content = filepath.read_text(encoding='utf-8')
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
    date_start = meta.get('date', filepath.stem)
    return {
        'date': date_start,
        'date_end': meta.get('date_end', ''),
        'date_display': format_date_range(date_start, meta.get('date_end', '')),
        'title': meta.get('title', filepath.stem),
        'tags': [t.strip() for t in re.split(r'[,，;；、]', meta.get('tags', '')) if t.strip()],
        'body': body,
        'html': markdown.markdown(body, extensions=['tables', 'fenced_code']),
    }


def generate():
    dailies = []
    for f in sorted(DAILY_DIR.glob('*.md')):
        dailies.append(parse_daily(f))

    docs = []
    for f in sorted(DOCS_DIR.iterdir()):
        if f.name == '.gitkeep':
            continue
        docs.append({'name': f.name, 'size': f.stat().st_size})

    # 统计
    all_tags = {}
    for d in dailies:
        for t in d['tags']:
            all_tags[t] = all_tags.get(t, 0) + 1

    total_days = len(dailies)
    date_range = ""
    if dailies:
        date_range = f"{dailies[0]['date']} ~ {dailies[-1]['date']}"

    # 按月分组
    months = {}
    for d in dailies:
        month_key = d['date'][:7]  # YYYY-MM
        if month_key not in months:
            months[month_key] = []
        months[month_key].append(d)

    # 生成 HTML
    tag_html = ''.join(f'<span class="tag">{t} ({c})</span>' for t, c in
                       sorted(all_tags.items(), key=lambda x: -x[1]))

    timeline_html = ''
    for month, entries in sorted(months.items()):
        timeline_html += f'<div class="month-group"><h3>{month}</h3>'
        for entry in entries:
            tags_str = ''.join(f'<span class="tag-sm">{t}</span>' for t in entry['tags'])
            timeline_html += f'''
            <div class="timeline-item">
                <div class="tl-date">{entry['date_display']}</div>
                <div class="tl-content">
                    <div class="tl-title">{entry['title']}</div>
                    <div class="tl-tags">{tags_str}</div>
                    <div class="tl-body">{entry['html']}</div>
                </div>
            </div>'''
        timeline_html += '</div>'

    docs_html = ''
    if docs:
        docs_html = '<ul class="doc-list">'
        for doc in docs:
            docs_html += f'<li>{doc["name"]} <span class="size">({doc["size"]/1024:.1f}KB)</span></li>'
        docs_html += '</ul>'

    # 项目经历
    projects_html = ''
    if PROJECTS_FILE.exists():
        projects_data = json.loads(PROJECTS_FILE.read_text(encoding='utf-8'))
        if projects_data.get('projects'):
            for p in projects_data['projects']:
                achievements_html = ''
                if p.get('achievements'):
                    achievements_html = '<ul class="proj-achievements">'
                    for a in p['achievements']:
                        achievements_html += f'<li>{a}</li>'
                    achievements_html += '</ul>'

                metrics_html = ''
                if p.get('metrics'):
                    metrics_html = '<div class="proj-metrics">'
                    for m in p['metrics']:
                        metrics_html += f'<span class="metric-badge">{m}</span>'
                    metrics_html += '</div>'

                skills_html = ''
                if p.get('skills'):
                    skills_html = '<div class="proj-skills">'
                    for s in p['skills']:
                        skills_html += f'<span class="tag-sm">{s}</span>'
                    skills_html += '</div>'

                projects_html += f'''
            <div class="project-card">
                <div class="proj-header">
                    <span class="proj-name">{p.get('project_name', '')}</span>
                    <span class="proj-time">{p.get('time_period', '')}</span>
                </div>
                <div class="proj-role">{p.get('role', '')}</div>
                <div class="proj-desc">{p.get('description', '')}</div>
                {achievements_html}
                {metrics_html}
                {skills_html}
            </div>'''

    html = REPORT_TEMPLATE.format(
        date_range=date_range,
        total_days=total_days,
        total_docs=len(docs),
        total_tags=len(all_tags),
        generated=datetime.now().strftime('%Y-%m-%d %H:%M'),
        tag_cloud=tag_html,
        timeline=timeline_html,
        docs_section=docs_html,
        projects_section=projects_html,
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / 'report.html'
    output_path.write_text(html, encoding='utf-8')
    print(f"[OK] 报告已生成: {output_path}")
    print(f"     共 {total_days} 篇日报, {len(docs)} 个文件, {len(all_tags)} 个标签")
    print(f"     时间范围: {date_range}")


REPORT_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>实习成长报告</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;700&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
<!-- PLACEHOLDER_STYLE -->
<style>
:root {{
    --bg: #faf8f5; --surface: #fff; --text: #2c2c2c;
    --muted: #8a8a8a; --accent: #e8590c; --accent-soft: #fff4e6;
    --border: #eee8e0; --radius: 12px;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Noto Serif SC',serif; background:var(--bg); color:var(--text); line-height:1.8; }}
.container {{ max-width:860px; margin:0 auto; padding:60px 24px; }}
header {{ text-align:center; margin-bottom:48px; }}
header h1 {{ font-size:2.4rem; margin-bottom:8px; }}
.subtitle {{ font-size:1.1rem; color:var(--accent); }}
.meta {{ font-size:0.8rem; color:var(--muted); margin-top:4px; }}
.stats {{ display:flex; justify-content:center; gap:48px; margin-bottom:48px; }}
.stat {{ text-align:center; }}
.stat .num {{ display:block; font-size:2.2rem; font-weight:700; color:var(--accent); font-family:'JetBrains Mono',monospace; }}
.stat .lbl {{ font-size:0.8rem; color:var(--muted); }}
section {{ margin-bottom:48px; }}
section h2 {{ font-size:1.3rem; margin-bottom:20px; padding-left:12px; border-left:4px solid var(--accent); }}
.tag-cloud {{ display:flex; flex-wrap:wrap; gap:8px; }}
.tag {{ padding:5px 14px; border-radius:16px; background:var(--accent-soft); color:var(--accent); font-size:0.82rem; }}
.month-group {{ margin-bottom:32px; }}
.month-group h3 {{ font-size:1rem; color:var(--muted); margin-bottom:12px; font-family:'JetBrains Mono',monospace; }}
.timeline-item {{ padding:20px 24px; background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); margin-bottom:12px; }}
.tl-date {{ font-family:'JetBrains Mono',monospace; font-size:0.78rem; color:var(--muted); }}
.tl-title {{ font-weight:700; margin-top:4px; }}
.tl-tags {{ margin-top:6px; display:flex; gap:4px; flex-wrap:wrap; }}
.tag-sm {{ font-size:0.7rem; padding:2px 8px; border-radius:10px; background:var(--accent-soft); color:var(--accent); }}
.tl-body {{ margin-top:12px; font-size:0.9rem; color:var(--text); }}
.tl-body h1,.tl-body h2,.tl-body h3 {{ font-size:1rem; margin-top:12px; }}
.tl-body ul {{ margin-left:20px; }}
.doc-list {{ list-style:none; }}
.doc-list li {{ padding:12px 16px; background:var(--surface); border:1px solid var(--border); border-radius:8px; margin-bottom:8px; }}
.doc-list .size {{ color:var(--muted); font-size:0.8rem; }}
.project-card {{ padding:24px; background:var(--surface); border:1px solid var(--border); border-left:4px solid var(--accent); border-radius:var(--radius); margin-bottom:16px; }}
.proj-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; }}
.proj-name {{ font-size:1.1rem; font-weight:700; }}
.proj-time {{ font-family:'JetBrains Mono',monospace; font-size:0.78rem; color:var(--muted); }}
.proj-role {{ font-size:0.85rem; color:var(--muted); margin-bottom:8px; }}
.proj-desc {{ font-size:0.9rem; margin-bottom:12px; }}
.proj-achievements {{ margin-left:20px; margin-bottom:12px; font-size:0.88rem; }}
.proj-achievements li {{ margin-bottom:4px; }}
.proj-metrics {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px; }}
.metric-badge {{ font-size:0.72rem; padding:3px 10px; border-radius:10px; background:#ebfbee; color:#2b8a3e; font-weight:700; }}
.proj-skills {{ display:flex; gap:6px; flex-wrap:wrap; }}
@media print {{ body {{ background:#fff; }} .container {{ padding:20px; }} }}
</style>
</head>
<body>
<div class="container">
    <header>
        <h1>实习成长报告</h1>
        <p class="subtitle">{date_range}</p>
        <p class="meta">生成于 {generated}</p>
    </header>

    <div class="stats">
        <div class="stat"><span class="num">{total_days}</span><span class="lbl">日报</span></div>
        <div class="stat"><span class="num">{total_docs}</span><span class="lbl">文件</span></div>
        <div class="stat"><span class="num">{total_tags}</span><span class="lbl">标签</span></div>
    </div>

    <section>
        <h2>技能标签</h2>
        <div class="tag-cloud">{tag_cloud}</div>
    </section>

    <section>
        <h2>成长时间线</h2>
        <div class="timeline">{timeline}</div>
    </section>

    <section>
        <h2>项目经历</h2>
        {projects_section}
    </section>

    <section>
        <h2>学习文件</h2>
        {docs_section}
    </section>
</div>
</body>
</html>'''


if __name__ == '__main__':
    generate()
