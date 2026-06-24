from __future__ import annotations

import argparse
import csv
import html
import json
from collections import defaultdict
from pathlib import Path


VARIANT_LABELS = {
    "full_choir": "四声部合成 / Full choir",
    "piano_reference": "钢琴参考 / Piano reference",
    "stem_soprano": "女高声部 / Soprano stem",
    "stem_alto": "女低声部 / Alto stem",
    "stem_tenor": "男高声部 / Tenor stem",
    "stem_bass": "男低声部 / Bass stem",
}
VARIANT_ORDER = ["full_choir", "piano_reference", "stem_soprano", "stem_alto", "stem_tenor", "stem_bass"]


def build_playback_index(package_dir: str | Path, *, strict: bool = True) -> Path:
    package = Path(package_dir)
    manifest_path = package / "audio_pro" / "pro_playback_manifest.csv"
    qc_path = package / "audio_pro" / "commercial_qc_summary.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    rows = read_manifest(manifest_path)
    if strict:
        validate_manifest_references(package, rows)
    qc = json.loads(qc_path.read_text(encoding="utf-8")) if qc_path.is_file() else {}
    scores = group_scores(rows)
    html_path = package / "score_audio_player.html"
    html_path.write_text(render_html(scores, qc), encoding="utf-8")
    return html_path


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def validate_manifest_references(package: Path, rows: list[dict[str, str]]) -> None:
    required_keys = ("mp3", "midi", "source_musicxml", "render_musicxml")
    missing: list[str] = []
    for row in rows:
        score_id = row.get("score_id", "UNKNOWN")
        variant = row.get("variant", "UNKNOWN")
        for key in required_keys:
            rel = row.get(key, "")
            if rel and not (package / rel).is_file():
                missing.append(f"{score_id}/{variant}: {key} -> {rel}")
    if missing:
        preview = "; ".join(missing[:10])
        suffix = f" and {len(missing) - 10} more" if len(missing) > 10 else ""
        raise FileNotFoundError(f"Playback index has missing referenced files: {preview}{suffix}")


def group_scores(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        key = (row["group"], row["score_id"])
        score = grouped.setdefault(
            key,
            {
                "group": row["group"],
                "score_id": row["score_id"],
                "source_musicxml": normalize_rel(row["source_musicxml"]),
                "render_musicxml": normalize_rel(row["render_musicxml"]),
                "pdf": infer_pdf_path(row["group"], row["score_id"]),
                "variants": {},
            },
        )
        variants = score["variants"]
        if isinstance(variants, dict):
            variants[row["variant"]] = {
                "mp3": normalize_rel(row["mp3"]),
                "midi": normalize_rel(row.get("midi", "")),
                "duration_sec": row["duration_sec"],
                "rms": row["rms"],
                "peak": row["peak"],
                "status": row["status"],
            }
    return [grouped[key] for key in sorted(grouped)]


def normalize_rel(value: str) -> str:
    return value.replace("\\", "/")


def infer_pdf_path(group: str, score_id: str) -> str:
    folder = "absolute_score_pdfs" if group == "absolute" else "paired_comparison_pdfs"
    return f"{folder}/{score_id}.pdf"


def render_html(scores: list[dict[str, object]], qc: dict[str, object]) -> str:
    data = json.dumps(scores, ensure_ascii=False)
    qc_score = html.escape(str(qc.get("qc_score", "NA")))
    pass_count = html.escape(str(qc.get("pass_count", "NA")))
    fail_count = html.escape(str(qc.get("fail_count", "NA")))
    variant_order = json.dumps(VARIANT_ORDER, ensure_ascii=False)
    variant_labels = json.dumps(VARIANT_LABELS, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Project1 SATB 乐谱-音频审阅台</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #5c6670;
      --line: #d8dde3;
      --panel: #f7f9fb;
      --accent: #0f766e;
      --accent-soft: #dff4ef;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      color: var(--ink);
      background: #ffffff;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 10;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      align-items: center;
      padding: 14px 18px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.96);
    }}
    h1 {{
      margin: 0;
      font-size: 18px;
      font-weight: 650;
      letter-spacing: 0;
    }}
    .subtitle {{
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
    }}
    .qc {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
      font-size: 13px;
      color: var(--muted);
    }}
    .qc span {{
      border: 1px solid var(--line);
      padding: 5px 8px;
      background: var(--panel);
    }}
    .toolbar {{
      display: grid;
      grid-template-columns: minmax(160px, 1fr) 150px;
      gap: 10px;
      padding: 12px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    input, select {{
      width: 100%;
      padding: 8px 10px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      font-size: 14px;
    }}
    main {{
      display: grid;
      grid-template-columns: 260px 1fr;
      min-height: calc(100vh - 103px);
    }}
    nav {{
      border-right: 1px solid var(--line);
      background: #fbfcfd;
      overflow: auto;
      max-height: calc(100vh - 103px);
    }}
    .nav-item {{
      width: 100%;
      border: 0;
      border-bottom: 1px solid var(--line);
      background: transparent;
      text-align: left;
      padding: 10px 12px;
      cursor: pointer;
      color: var(--ink);
      font-size: 13px;
    }}
    .nav-item.active {{
      background: var(--accent-soft);
      border-left: 4px solid var(--accent);
      padding-left: 8px;
    }}
    section {{
      padding: 18px;
      overflow: auto;
    }}
    .score-head {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 12px;
      margin-bottom: 14px;
    }}
    .score-title {{
      font-size: 22px;
      font-weight: 700;
      margin: 0;
    }}
    .links {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
      border-bottom: 1px solid transparent;
    }}
    a:hover {{ border-bottom-color: var(--accent); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(260px, 1fr));
      gap: 12px;
    }}
    .track {{
      border: 1px solid var(--line);
      padding: 12px;
      background: #fff;
    }}
    .track h3 {{
      margin: 0 0 8px 0;
      font-size: 15px;
      font-weight: 650;
    }}
    audio {{
      width: 100%;
      height: 36px;
    }}
    .meta {{
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
    }}
    .empty {{
      color: var(--muted);
      padding: 28px;
      text-align: center;
    }}
    @media (max-width: 800px) {{
      header {{ grid-template-columns: 1fr; }}
      .qc {{ justify-content: flex-start; }}
      main {{ grid-template-columns: 1fr; }}
      nav {{ max-height: 220px; border-right: 0; border-bottom: 1px solid var(--line); }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Project1 SATB 乐谱-音频审阅台</h1>
      <div class="subtitle">专家审阅用离线播放器：同一首乐谱对应全声部、钢琴参考和四个单声部音频</div>
    </div>
    <div class="qc">
      <span>QC score: {qc_score}/100</span>
      <span>通过: {pass_count}</span>
      <span>失败: {fail_count}</span>
    </div>
  </header>
  <div class="toolbar">
    <input id="search" placeholder="搜索谱例编号，例如 P1S01 或 P1P09_A">
    <select id="groupFilter">
      <option value="all">全部谱例</option>
      <option value="absolute">逐首评分</option>
      <option value="paired">A/B 配对比较</option>
    </select>
  </div>
  <main>
    <nav id="scoreList"></nav>
    <section id="detail" class="empty">请选择左侧谱例。</section>
  </main>
  <script>
    const scores = {data};
    const variantOrder = {variant_order};
    const variantLabels = {variant_labels};
    let filtered = scores.slice();
    let activeIndex = 0;

    function filterScores() {{
      const q = document.getElementById('search').value.trim().toLowerCase();
      const group = document.getElementById('groupFilter').value;
      filtered = scores.filter(s => {{
        const matchesText = !q || s.score_id.toLowerCase().includes(q) || s.group.toLowerCase().includes(q);
        const matchesGroup = group === 'all' || s.group === group;
        return matchesText && matchesGroup;
      }});
      activeIndex = 0;
      renderList();
      renderDetail();
    }}

    function renderList() {{
      const list = document.getElementById('scoreList');
      list.innerHTML = '';
      if (!filtered.length) {{
        list.innerHTML = '<div class="empty">没有匹配的谱例。</div>';
        return;
      }}
      filtered.forEach((score, idx) => {{
        const button = document.createElement('button');
        button.className = 'nav-item' + (idx === activeIndex ? ' active' : '');
        button.textContent = `${{score.score_id}} | ${{score.group}}`;
        button.onclick = () => {{
          activeIndex = idx;
          renderList();
          renderDetail();
        }};
        list.appendChild(button);
      }});
    }}

    function renderDetail() {{
      const detail = document.getElementById('detail');
      if (!filtered.length) {{
        detail.className = 'empty';
        detail.textContent = '没有匹配的谱例。';
        return;
      }}
      detail.className = '';
      const score = filtered[activeIndex];
      const tracks = variantOrder.map(name => {{
        const item = score.variants[name];
        if (!item) return '';
        return `<div class="track">
          <h3>${{variantLabels[name] || name}}</h3>
          <audio controls preload="none" src="${{item.mp3}}"></audio>
          <div class="meta">时长 ${{item.duration_sec}}s | 峰值 ${{item.peak}} | 状态 ${{item.status}}</div>
          <div class="meta"><a href="${{item.midi}}" target="_blank">下载 MIDI</a></div>
        </div>`;
      }}).join('');
      detail.innerHTML = `<div class="score-head">
        <div>
          <h2 class="score-title">${{score.score_id}}</h2>
          <div class="meta">${{score.group}} | score-level SATB playback assets</div>
        </div>
        <div class="links">
          <a href="${{score.pdf}}" target="_blank">查看 PDF</a>
          <a href="${{score.source_musicxml}}" target="_blank">查看源 MusicXML</a>
          <a href="${{score.render_musicxml}}" target="_blank">查看渲染 MusicXML</a>
        </div>
      </div>
      <div class="grid">${{tracks}}</div>`;
    }}

    document.getElementById('search').addEventListener('input', filterScores);
    document.getElementById('groupFilter').addEventListener('change', filterScores);
    filterScores();
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local static playback console for pro playback assets.")
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--allow-missing", action="store_true", help="Build the HTML index without checking file refs.")
    args = parser.parse_args()
    print(build_playback_index(args.package_dir, strict=not args.allow_missing))


if __name__ == "__main__":
    main()
