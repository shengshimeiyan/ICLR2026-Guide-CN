# -*- coding: utf-8 -*-
"""
ACL 2026 全量论文 · 两级目录静态网页渲染
=========================================
输入：ACL2026_all_papers.json + 可选 ACL2026_all_papers_CN.json
输出：index.html（直接覆盖）

侧边栏：研究方向 / 小类双层折叠树
主体：嵌套 section + 论文卡
保留：搜索 / track 筛选 / 六维度展示 / 折叠完整摘要 / GoatCounter 访问统计
"""

import json
import os
import re
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from urllib.parse import quote

INPUT_JSON = os.environ.get("INPUT_JSON", "ACL2026_all_papers.json")
CN_OVERLAY_JSON = os.environ.get("CN_OVERLAY_JSON", "ACL2026_all_papers_CN.json")
OUTPUT_HTML = os.environ.get("OUTPUT_HTML", "index.html")

# 6 个分析维度（与 translate_all_papers.py 输出对齐）
DIM_LABELS = [
    ("研究动机",     "🎯 研究动机"),
    ("解决问题",     "❓ 解决问题"),
    ("现象分析",     "🔍 现象分析"),
    ("主要方法",     "🛠️ 主要方法"),
    ("数据集与实验", "📊 数据与实验"),
    ("主要贡献",     "⭐ 主要贡献"),
]

# 兜底翻译（保留给兼容旧数据或手工导入数据）
PRIMARY_AREA_FALLBACK_ZH = {}

def _norm_primary(p):
    p = (p or "").strip()
    if not p:
        return "(未填)"
    return PRIMARY_AREA_FALLBACK_ZH.get(p, p)


def normalize_search_text(text):
    text = (text or "").lower()
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def short_track_label(track):
    track = (track or "Unknown Track").strip()
    lower = track.lower()
    if "findings of the association" in lower or track == "Findings":
        return "Findings"
    if "volume 1: long papers" in lower:
        return "Main Long"
    if "volume 2: short papers" in lower:
        return "Main Short"
    if "volume 3: system demonstrations" in lower:
        return "Demo"
    if "volume 4: student research workshop" in lower:
        return "SRW"
    if "volume 5: tutorial abstracts" in lower:
        return "Tutorial"
    if "volume 6: industry track" in lower:
        return "Industry"
    if track == "Main Conference":
        return "Main"
    if track.endswith(" 2026") and len(track) <= 28:
        return track.replace(" 2026", "")
    if "(" in track and ")" in track:
        inside = track.rsplit("(", 1)[-1].split(")", 1)[0].strip()
        if 2 <= len(inside) <= 24:
            return inside
    prefixes = [
        "Proceedings of the ",
        "Proceedings of ",
        "The ",
    ]
    label = track
    for prefix in prefixes:
        if label.startswith(prefix):
            label = label[len(prefix):]
            break
    return label[:36] + "..." if len(label) > 39 else label


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#f6f8fa;color:#24292e;line-height:1.7}
.container{display:flex;min-height:100vh}
.sidebar{width:320px;background:#fff;border-right:1px solid #e1e4e8;padding:24px 18px;position:sticky;top:0;height:100vh;overflow-y:auto}
.sidebar h1{font-size:18px;margin-bottom:6px;color:#0366d6;line-height:1.3;font-weight:700}
.sidebar .sub{font-size:12px;color:#6a737d;margin-bottom:16px}
.sidebar input[type=search]{width:100%;padding:9px 12px;border:1px solid #d1d5da;border-radius:6px;margin-bottom:14px;font-size:13px;outline:none}
.sidebar input[type=search]:focus{border-color:#0366d6;box-shadow:0 0 0 2px rgba(3,102,214,.2)}
.stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:16px}
.stat-box{background:#f6f8fa;padding:8px 10px;border-radius:6px;font-size:11px;color:#586069}
.stat-box b{color:#0366d6;font-size:14px;display:block}

/* 两级树状导航 */
.nav-tree{font-size:13px}
.nav-pri{margin-bottom:4px;border-radius:5px;overflow:hidden}
.nav-pri-head{display:flex;align-items:center;cursor:pointer;padding:7px 10px;background:#f6f8fa;border-radius:5px;font-weight:600;color:#24292e;user-select:none;transition:background .15s}
.nav-pri-head:hover{background:#e7f3ff}
.nav-pri-head .arrow{margin-right:6px;font-size:10px;color:#959da5;transition:transform .2s}
.nav-pri.expanded > .nav-pri-head .arrow{transform:rotate(90deg)}
.nav-pri-head .name{flex:1}
.nav-pri-head .count{color:#6a737d;font-size:11px;background:#eaecef;padding:2px 8px;border-radius:10px;font-weight:500}
.nav-sub-list{display:none;padding:4px 0 6px 24px}
.nav-pri.expanded > .nav-sub-list{display:block}
.nav-sub-list a{display:flex;align-items:center;padding:5px 8px;color:#586069;text-decoration:none;border-radius:4px;font-size:12.5px;margin-bottom:1px;transition:background .15s}
.nav-sub-list a:hover{background:#f1f4f7;color:#0366d6}
.nav-sub-list a .name{flex:1}
.nav-sub-list a .count{color:#959da5;font-size:11px;margin-left:6px}

.main{flex:1;padding:32px 44px;max-width:calc(100% - 320px)}
.main-header{margin-bottom:32px;padding-bottom:18px;border-bottom:1px solid #e1e4e8}
.main-header h1{font-size:28px;margin-bottom:10px}
.main-header p{color:#586069;font-size:14px}
.info-panel{background:#fff;border:1px solid #e1e4e8;border-radius:8px;padding:14px 16px;margin:18px 0;box-shadow:0 1px 2px rgba(0,0,0,.03)}
.info-panel h2{font-size:15px;margin-bottom:6px;color:#24292e}
.info-panel p{font-size:12.5px;color:#586069;margin:0}
.area-chart{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:9px 18px;margin-top:12px}
.area-row{display:grid;grid-template-columns:minmax(96px,1fr) 120px 44px;align-items:center;gap:8px;font-size:12px}
.area-name{color:#24292e;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.area-track{height:8px;background:#eaecef;border-radius:99px;overflow:hidden}
.area-bar{height:100%;background:#0366d6;border-radius:99px}
.area-count{color:#6a737d;text-align:right;font-variant-numeric:tabular-nums}
.filter-title{font-size:12px;font-weight:700;color:#586069;margin:18px 0 8px}
.filter-hint{font-size:11px;color:#959da5;margin-top:6px}

h2.pri-title{font-size:24px;color:#0366d6;border-bottom:2px solid #0366d6;padding-bottom:8px;margin:40px 0 12px;scroll-margin-top:20px}
h2.pri-title small{font-size:13px;color:#6a737d;font-weight:400;margin-left:8px}
h3.sub-title{font-size:18px;color:#24292e;border-left:4px solid #0366d6;padding:4px 12px;margin:24px 0 14px;scroll-margin-top:20px;background:#f6f8fa;border-radius:0 4px 4px 0}
h3.sub-title small{font-size:12px;color:#6a737d;font-weight:400;margin-left:8px}

.paper{background:#fff;border:1px solid #e1e4e8;border-radius:8px;padding:18px 22px;margin-bottom:14px;box-shadow:0 1px 2px rgba(0,0,0,.04);transition:box-shadow .15s;position:relative}
.paper:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}
.paper.tier-Oral{border-left:4px solid #d4a017;background:linear-gradient(to right, #fffaeb 0, #fff 80px)}
.paper.tier-Spotlight{border-left:4px solid #5b8def}
.tier-badge{display:inline-block;font-weight:700;font-size:11px;padding:2px 9px;border-radius:10px;margin-right:6px;letter-spacing:.3px;vertical-align:middle}
.tier-badge.Oral{background:#fff4d4;color:#8a6500;border:1px solid #d4a017}
.tier-badge.Spotlight{background:#e7f0ff;color:#1f4dad;border:1px solid #5b8def}

/* 顶部档次摘要 */
.tier-summary{margin:18px 0;display:flex;gap:8px;flex-wrap:wrap}
.tier-chip{display:inline-flex;align-items:center;padding:5px 12px;border-radius:14px;font-size:12px;font-weight:600;cursor:pointer;user-select:none;border:1px solid transparent;transition:all .15s}
.tier-chip{background:#f6f8fa;color:#586069;border-color:#d1d5da}
.tier-chip.active{background:#0366d6;color:#fff;border-color:#0366d6}
.tier-chip.all{background:#eaecef;color:#24292e}
.tier-chip.all.active{background:#0366d6;color:#fff}
.tier-chip.Oral{background:#fff4d4;color:#8a6500;border-color:#d4a017}
.tier-chip.Oral.active{background:#d4a017;color:#fff}
.tier-chip.Spotlight{background:#e7f0ff;color:#1f4dad;border-color:#5b8def}
.tier-chip.Spotlight.active{background:#5b8def;color:#fff}
.tier-chip:hover{transform:translateY(-1px)}
.paper-title{font-size:16px;font-weight:600;color:#24292e;margin-bottom:8px;line-height:1.45}
.paper-title a{color:inherit;text-decoration:none}
.paper-title a:hover{color:#0366d6;text-decoration:underline}
.paper-meta{font-size:12px;color:#586069;margin-bottom:10px}
.paper-meta .badge{display:inline-block;background:#e7f3ff;color:#0366d6;padding:2px 8px;border-radius:10px;margin-right:5px;font-size:11px;font-weight:500}
.paper-meta .badge.sub{background:#eaecef;color:#24292e}
.paper-meta .kw{color:#6a737d;margin-right:6px}
.paper-tldr{background:#fffbea;border-left:3px solid #f9c513;padding:9px 13px;font-size:13px;color:#735c0f;margin-bottom:11px;border-radius:0 4px 4px 0}
.paper-tldr b{color:#5a4500}
.dim{margin:8px 0;font-size:13.5px;display:flex;gap:10px;align-items:flex-start}
.dim-label{flex-shrink:0;font-weight:600;color:#0366d6;width:96px;font-size:12.5px;padding-top:1px}
.dim-content{flex:1;color:#24292e}
.toggle-abs{font-size:12px;color:#0366d6;cursor:pointer;margin-top:10px;display:inline-block;user-select:none;padding:3px 8px;border-radius:4px}
.toggle-abs:hover{background:#e7f3ff}
.full-abs{display:none;margin-top:10px;padding:11px 14px;background:#f6f8fa;border-radius:5px;font-size:12.5px;color:#444;line-height:1.65;border-left:3px solid #d1d5da}
.paper.expanded .full-abs{display:block}
.paper.expanded .toggle-abs::before{content:"▾ "}
.paper:not(.expanded) .toggle-abs::before{content:"▸ "}
.hidden{display:none !important}
.empty{text-align:center;color:#959da5;padding:40px;font-size:14px}
.no-cn{font-style:italic;color:#959da5}

@media(max-width:900px){
  .container{flex-direction:column}
  .sidebar{width:100%;height:auto;position:relative}
  .main{max-width:100%;padding:20px}
  .area-row{grid-template-columns:minmax(90px,1fr) 90px 40px}
  .dim{flex-direction:column;gap:4px}
  .dim-label{width:auto}
}
"""


JS = """
const search=document.getElementById('search');
const tierChips=document.querySelectorAll('.tier-chip');
const quickCn=document.getElementById('quick-cn');
const quickMainFindings=document.getElementById('quick-main-findings');
const clearFilters=document.getElementById('clear-filters');
const resultCount=document.getElementById('result-count');
const filterSummary=document.getElementById('filter-summary');
const results=document.getElementById('results');
const loadMore=document.getElementById('load-more');

const BATCH_SIZE=80;
const DIM_LABELS=[
  ['研究动机','🎯 研究动机'],
  ['解决问题','❓ 解决问题'],
  ['现象分析','🔍 现象分析'],
  ['主要方法','🛠️ 主要方法'],
  ['数据集与实验','📊 数据与实验'],
  ['主要贡献','⭐ 主要贡献']
];

let activeTrack='__all__';
let activePrimary='';
let activeCategory='';
let onlyCn=false;
let mainFindingsOnly=false;
let renderedCount=0;
let currentMatches=[];

function esc(s){
  return String(s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function normalizeSearchText(s){
  return String(s||'').toLowerCase().replace(/\\s*-\\s*/g,'-').replace(/\\s+/g,' ').trim();
}

// 大类折叠/展开
document.querySelectorAll('.nav-pri-head').forEach(h=>{
  h.addEventListener('click', e=>{
    if(e.target.closest('.nav-sub-list')) return;
    h.parentElement.classList.toggle('expanded');
  });
});

document.querySelectorAll('.nav-filter').forEach(a=>{
  a.addEventListener('click', e=>{
    e.preventDefault();
    activePrimary=a.dataset.primary||'';
    activeCategory=a.dataset.category||'';
    renderedCount=0;
    applyFilters();
    document.getElementById('results-panel').scrollIntoView({behavior:'smooth',block:'start'});
  });
});

function matchesPaper(p, q){
  const matchSearch=!q || (p.search||'').includes(q);
  const matchTrack=(activeTrack==='__all__') || (p.track===activeTrack);
  const matchPrimary=!activePrimary || p.primary===activePrimary;
  const matchCategory=!activeCategory || p.category===activeCategory;
  const matchCn=!onlyCn || !!p.analysis;
  const matchMainFindings=!mainFindingsOnly || p.trackLabel.startsWith('Main') || p.trackLabel==='Findings';
  return matchSearch && matchTrack && matchPrimary && matchCategory && matchCn && matchMainFindings;
}

function paperCard(p){
  const authors=(p.authors||[]).join('、');
  const kws=(p.keywords||[]).map(k=>`<span class="kw">#${esc(k)}</span>`).join(' ');
  const tldr=p.tldr ? `<div class="paper-tldr"><b>TL;DR：</b>${esc(p.tldr)}</div>` : '';
  let dims='<div class="dim no-cn">（中文六维度分析尚未生成）</div>';
  if(p.analysis){
    dims=DIM_LABELS.map(([key,label])=>{
      return `<div class="dim"><span class="dim-label">${label}</span><div class="dim-content">${esc(p.analysis[key]||'')}</div></div>`;
    }).join('');
  }
  return `<${'article'} class="paper">
    <div class="paper-title"><span class="tier-badge Spotlight" title="${esc(p.track)}">${esc(p.trackLabel)}</span><a href="${esc(p.url||'#')}" target="_blank">${esc(p.title)}</a></div>
    <div class="paper-meta">
      <span class="badge">${esc(p.primary)}</span>
      <span class="badge sub">${esc(p.category)}</span>
      ${authors ? `<span class="kw">${esc(authors)}</span>` : ''}
      ${kws}
    </div>
    ${tldr}
    ${dims}
    <span class="toggle-abs" onclick="this.parentElement.classList.toggle('expanded')">查看完整摘要 (Abstract)</span>
    <div class="full-abs">${esc(p.abstract||'')}</div>
  </${'article'}>`;
}

function renderMore(){
  const next=currentMatches.slice(renderedCount, renderedCount+BATCH_SIZE);
  results.insertAdjacentHTML('beforeend', next.map(paperCard).join(''));
  renderedCount += next.length;
  loadMore.classList.toggle('hidden', renderedCount>=currentMatches.length);
}

function describeFilters(){
  const parts=[];
  if(activePrimary) parts.push(activeCategory ? `${activePrimary} / ${activeCategory}` : activePrimary);
  if(activeTrack!=='__all__'){
    const p=PAPERS.find(x=>x.track===activeTrack);
    parts.push(p ? p.trackLabel : activeTrack);
  }
  if(onlyCn) parts.push('有中文分析');
  if(mainFindingsOnly) parts.push('Main/Findings');
  return parts.length ? parts.join(' · ') : '全部论文';
}

function applyFilters(){
  const q=normalizeSearchText(search.value||'');
  currentMatches=PAPERS.filter(p=>matchesPaper(p,q));
  renderedCount=0;
  results.innerHTML='';
  resultCount.textContent=`${currentMatches.length} / ${PAPERS.length} 篇`;
  filterSummary.textContent=describeFilters();
  renderMore();
  if(currentMatches.length===0){
    results.innerHTML='<div class="empty">没有匹配的论文。试试清除筛选或缩短搜索词。</div>';
    loadMore.classList.add('hidden');
  }
}

search.addEventListener('input', applyFilters);
tierChips.forEach(chip=>{
  chip.addEventListener('click', ()=>{
    activeTrack = chip.dataset.tier;
    tierChips.forEach(c => c.classList.toggle('active', c===chip));
    renderedCount=0;
    applyFilters();
  });
});
quickCn.addEventListener('click',()=>{
  onlyCn=!onlyCn;
  quickCn.classList.toggle('active', onlyCn);
  applyFilters();
});
quickMainFindings.addEventListener('click',()=>{
  mainFindingsOnly=!mainFindingsOnly;
  quickMainFindings.classList.toggle('active', mainFindingsOnly);
  applyFilters();
});
clearFilters.addEventListener('click',()=>{
  activeTrack='__all__';
  activePrimary='';
  activeCategory='';
  onlyCn=false;
  mainFindingsOnly=false;
  search.value='';
  tierChips.forEach(c => c.classList.toggle('active', c.dataset.tier==='__all__'));
  quickCn.classList.remove('active');
  quickMainFindings.classList.remove('active');
  applyFilters();
});
loadMore.addEventListener('click', renderMore);
applyFilters();
"""


def build():
    data = json.loads(Path(INPUT_JSON).read_text(encoding="utf-8"))
    papers = data["papers"]

    # 叠加中文分析（如果 CN overlay 存在）
    cn_map = {}
    if Path(CN_OVERLAY_JSON).exists():
        cn_data = json.loads(Path(CN_OVERLAY_JSON).read_text(encoding="utf-8"))
        cn_map = {p["id"]: p.get("中文分析") for p in cn_data.get("papers", []) if p.get("中文分析")}
    n_with_cn = 0
    for p in papers:
        if p["id"] in cn_map:
            p["中文分析"] = cn_map[p["id"]]
            n_with_cn += 1

    # 兜底翻译
    for p in papers:
        p["primary_area"] = _norm_primary(p.get("primary_area"))
        p["category"] = (p.get("category") or "(未分类)").strip()

    # 按 primary_area → category 分组
    grouped = defaultdict(lambda: defaultdict(list))
    for p in papers:
        grouped[p["primary_area"]][p["category"]].append(p)

    # 大类排序：按论文数降序
    primary_order = [pa for pa, _ in Counter(p["primary_area"] for p in papers).most_common()]

    total = len(papers)
    n_pri = len(primary_order)
    n_sub_total = sum(len(subs) for subs in grouped.values())
    primary_cnt = Counter(p["primary_area"] for p in papers)
    max_primary = max(primary_cnt.values()) if primary_cnt else 1
    area_chart_html = []
    for pa in primary_order:
        count = primary_cnt[pa]
        pct = count * 100 / total if total else 0
        width = max(2, count * 100 / max_primary)
        area_chart_html.append(
            f'<div class="area-row">'
            f'<span class="area-name" title="{escape(pa)}">{escape(pa)}</span>'
            f'<span class="area-track"><span class="area-bar" style="width:{width:.1f}%"></span></span>'
            f'<span class="area-count">{count} · {pct:.1f}%</span>'
            f'</div>'
        )
    track_cnt = Counter((p.get("track") or "Unknown Track").strip() for p in papers)
    track_chips = "".join(
        f'<span class="tier-chip" data-tier="{escape(track)}" title="{escape(track)}">'
        f'{escape(short_track_label(track))} {count} 篇</span>'
        for track, count in track_cnt.most_common()
    )
    source_label = escape(str(INPUT_JSON))

    # ---- 侧边栏 ----
    nav_html = []
    for pa in primary_order:
        sub_dict = grouped[pa]
        # 小类排序：先按数量降序，"其他"放最后
        subs_sorted = sorted(
            sub_dict.items(),
            key=lambda kv: (kv[0] == "其他" or kv[0].startswith("其他"), -len(kv[1]), kv[0])
        )
        pa_anchor = "pri-" + quote(pa, safe="")
        pa_count = sum(len(v) for v in sub_dict.values())
        sub_links = []
        for sub, items in subs_sorted:
            sub_anchor = "sub-" + quote(pa, safe="") + "-" + quote(sub, safe="")
            sub_links.append(
                f'<a href="#results-panel" class="nav-filter" data-primary="{escape(pa)}" data-category="{escape(sub)}">'
                f'<span class="name">{escape(sub)}</span>'
                f'<span class="count">({len(items)})</span></a>'
            )
        nav_html.append(f"""
<div id="nav-{pa_anchor}" class="nav-pri">
  <div class="nav-pri-head">
    <span class="arrow">▶</span>
    <span class="name">{escape(pa)}</span>
    <span class="count">{pa_count}</span>
  </div>
  <div class="nav-sub-list">{''.join(sub_links)}</div>
</div>""")

    compact_papers = []
    for p in papers:
        track = (p.get("track") or "Unknown Track").strip()
        authors = p.get("authors", []) or []
        keywords = p.get("keywords", []) or []
        analysis = p.get("中文分析") or None
        search_blob = normalize_search_text(
            p.get("title", "") + " " + " ".join(keywords) + " " + (p.get("tldr") or "") + " "
            + p.get("primary_area", "") + " " + p.get("category", "") + " " + track + " "
            + short_track_label(track) + " " + " ".join(authors)
        )
        compact_papers.append({
            "id": p.get("id", ""),
            "title": p.get("title", ""),
            "url": p.get("url", "#"),
            "authors": authors,
            "track": track,
            "trackLabel": short_track_label(track),
            "primary": p.get("primary_area", ""),
            "category": p.get("category", ""),
            "keywords": keywords,
            "tldr": p.get("tldr") or "",
            "abstract": p.get("abstract", "") or "",
            "analysis": analysis,
            "search": search_blob,
        })
    papers_json = json.dumps(compact_papers, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ACL 2026 论文集 · 中文导读（{total} 篇）</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
  <aside class="sidebar">
    <h1>📚 ACL 2026<br>全部论文中文导读</h1>
    <div class="sub">{total} 篇 · {n_pri} 个大类 · {n_sub_total} 个细分</div>
    <input type="search" id="search" placeholder="🔍 搜索标题 / 关键词…">
    <div class="stat-grid">
      <div class="stat-box"><b>{total}</b>论文总数</div>
      <div class="stat-box"><b>{n_pri}</b>大类</div>
    </div>
    <div style="font-size:12px;font-weight:600;color:#586069;margin-bottom:8px">📁 按 NLP/CL 研究方向浏览</div>
    <div class="nav-tree">{''.join(nav_html)}</div>
    <div style="margin-top:24px;padding-top:16px;border-top:1px solid #eaecef;font-size:11px;color:#959da5;line-height:1.6">
      📊 数据来源：<br>ACL Anthology · ACL 2026<br>
      （公开论文以 ACL Anthology 页面为准）<br><br>
      💡 每篇论文的"六维度"由大语言模型基于 abstract 自动生成，仅供快速浏览，详见原文。<br><br>
      <span id="visit-stats" style="display:none">👁 总访问 <b id="gc-pv" style="color:#0366d6"></b> 次　·　访客 <b id="gc-uv" style="color:#0366d6"></b> 人</span>
    </div>
    <script data-goatcounter="https://jenniferzhao0531.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
    <script>
    fetch('https://jenniferzhao0531.goatcounter.com/counter/TOTAL.json')
      .then(r => r.json()).then(d => {{
        document.getElementById('gc-pv').textContent = (d.count || '0').toString().replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ',');
        document.getElementById('gc-uv').textContent = (d.count_unique || '0').toString().replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ',');
        document.getElementById('visit-stats').style.display = 'inline';
      }}).catch(()=>{{}});
    </script>
  </aside>
  <main class="main">
    <div class="main-header">
      <h1>ACL 2026 全部论文 · 中文导读</h1>
      <p>优先从 ACL Anthology 拉取 ACL 2026 公开论文，共 <b>{total}</b> 篇，按 NLP/计算语言学研究方向（{n_pri} 个大类）整理。每篇论文给出"研究动机 / 解决问题 / 现象分析 / 主要方法 / 数据集与实验 / 主要贡献"六个维度的中文分析。中文内容由大语言模型基于英文 abstract 自动生成，仅供快速浏览参考，建议结合原文阅读。左侧导航点大类标题展开/收起子项；点击论文标题直达 ACL Anthology 原文。</p>
      <div class="info-panel">
        <h2>大类分布</h2>
        <p>当前页面读取 <code>{source_label}</code>，按优化后的一级研究方向统计。条形长度按最大大类归一化，方便快速观察分布。</p>
        <div class="area-chart">{''.join(area_chart_html)}</div>
      </div>
      <div class="info-panel">
        <h2>一级分类优化说明</h2>
        <p>一级分类采用“语义研究方向优先”的口径：只有主要贡献是基础模型本身的预训练、架构、对齐、推理机制、Agent、长上下文或效率时，才归入大语言模型与基础模型；如果 LLM 只是方法或工具，则按论文真正的任务、应用、评测对象或领域归类。</p>
      </div>
      <div class="filter-title">Track 筛选</div>
      <div class="tier-summary">
        <span class="tier-chip all active" data-tier="__all__">📚 全部 {total} 篇</span>
        {track_chips}
      </div>
      <div class="filter-hint">点击任一 track 只显示对应来源；再次点击“全部”恢复全量。搜索框会和 track 筛选叠加生效。</div>
      <div class="filter-title">快捷筛选</div>
      <div class="tier-summary">
        <button id="quick-cn" class="tier-chip" type="button">只看有中文分析</button>
        <button id="quick-main-findings" class="tier-chip" type="button">只看 Main/Findings</button>
        <button id="clear-filters" class="tier-chip" type="button">清除筛选</button>
      </div>
    </div>
    <section id="results-panel">
      <h2 class="pri-title">论文列表 <small id="result-count">{total} / {total} 篇</small></h2>
      <div class="filter-hint">当前筛选：<span id="filter-summary">全部论文</span>。为提升加载速度，页面每次只渲染前 80 条结果。</div>
      <div id="results"></div>
      <button id="load-more" class="tier-chip all" type="button">加载更多</button>
    </section>
  </main>
</div>
<script>const PAPERS = {papers_json};</script>
<script>{JS}</script>
</body>
</html>
"""

    Path(OUTPUT_HTML).write_text(html, encoding="utf-8")
    print(f"[OK] 已生成 {OUTPUT_HTML}（{total} 篇 · {n_pri} 大类 · {n_sub_total} 细分 · {n_with_cn} 篇带中文分析）")
    if n_with_cn < total:
        print(f"   提示：还有 {total - n_with_cn} 篇没有中文六维度分析，等 translate_all_papers.py 跑完后再重新 build。")


if __name__ == "__main__":
    build()
