"""Build web-optimized static artifacts (optional Pages; local-first)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mainframe import __version__
from mainframe.config import ROOT
from mainframe.recommend.modes import MODE_DETERMINISTIC
from mainframe.surfaces.catalog import SURFACE_WEB, WEB_FOCUS

WEB_DIST = ROOT / "dist" / "web"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_web_surface(dest: Path | None = None) -> dict[str, Any]:
    out = dest or WEB_DIST
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    # Copy web-relevant docs + held-out site fixture as demo content
    site_src = ROOT / "docs" / "eval" / "workloads" / "holdout" / "w2_site_maint"
    demos = out / "demos" / "site_maintenance"
    demos.mkdir(parents=True, exist_ok=True)
    if site_src.is_dir():
        for p in site_src.iterdir():
            if p.is_file():
                shutil.copy2(p, demos / p.name)

    # Static landing optimized for web/webapp audiences
    index = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MAINFRAME · Web surface</title>
  <meta name="description" content="FreeForge web surface — websites and web applications, local-first." />
  <style>
    :root {{
      --ink:#0f1a16; --paper:#e8f2ec; --accent:#1f6b4a; --mute:#5a7166;
      --line:#c5d9ce;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0; font-family:"IBM Plex Sans","Segoe UI",sans-serif;
      color:var(--ink);
      background:
        radial-gradient(1200px 600px at 10% -10%, #cfe8da 0%, transparent 55%),
        linear-gradient(180deg, #f4faf6, var(--paper));
      min-height:100vh;
    }}
    .hero {{
      min-height:100vh; display:flex; flex-direction:column; justify-content:center;
      padding:clamp(1.5rem,4vw,4rem); max-width:56rem;
    }}
    .brand {{
      font-family:"IBM Plex Serif",Georgia,serif; font-size:clamp(2.8rem,8vw,5rem);
      line-height:.95; letter-spacing:-.02em; margin:0 0 .75rem;
    }}
    .tag {{ color:var(--accent); font-weight:600; text-transform:uppercase;
      letter-spacing:.12em; font-size:.8rem; margin-bottom:1rem; }}
    h1 {{ font-size:clamp(1.35rem,3vw,1.85rem); font-weight:550; max-width:28ch;
      margin:0 0 1rem; line-height:1.25; }}
    p {{ color:var(--mute); max-width:42rem; font-size:1.05rem; line-height:1.55; }}
    .cta {{ display:flex; flex-wrap:wrap; gap:.75rem; margin-top:1.75rem; }}
    a.btn {{
      text-decoration:none; color:#fff; background:var(--accent);
      padding:.7rem 1.1rem; border-radius:2px; font-weight:600;
    }}
    a.ghost {{ background:transparent; color:var(--ink); border:1px solid var(--line); }}
    section {{ padding:clamp(1.5rem,4vw,3rem); border-top:1px solid var(--line); max-width:56rem; }}
    h2 {{ font-size:1.2rem; margin:0 0 .75rem; }}
    ul {{ color:var(--mute); line-height:1.6; }}
    code {{ font-family:"IBM Plex Mono",Consolas,monospace; font-size:.9em; }}
  </style>
</head>
<body>
  <div class="hero">
    <div class="tag">Web surface · v{__version__}</div>
    <p class="brand">MAINFRAME</p>
    <h1>Built for websites and web applications — not a generic dashboard wall.</h1>
    <p>
      Deterministic local automation for site maintenance, browser evidence, HTTP connectors,
      and web-oriented workflows. Optional CPU AI pauses when unavailable. No required paid hosting.
    </p>
    <div class="cta">
      <a class="btn" href="demos/site_maintenance/index.html">Open site demo</a>
      <a class="btn ghost" href="manifest.json">Surface manifest</a>
    </div>
  </div>
  <section>
    <h2>Optimized for</h2>
    <ul>
      {''.join(f'<li>{x}</li>' for x in WEB_FOCUS['optimized_for'])}
    </ul>
    <p>Recommended FreeForge mode: <code>{MODE_DETERMINISTIC}</code> until a local model is measured.</p>
    <p>GitHub Pages hosting is <strong>optional</strong> — not required to run MAINFRAME locally.</p>
  </section>
</body>
</html>
"""
    (out / "index.html").write_text(index, encoding="utf-8")

    # 404 for Pages
    (out / "404.html").write_text(
        "<!DOCTYPE html><html><body><p>MAINFRAME web surface — page not found. "
        "<a href=\"./\">Home</a></p></body></html>\n",
        encoding="utf-8",
    )

    # Copy recommend + heldout summaries if present
    for name in ("FREEFORGE_RECOMMENDED.md", "COST_AUDIT.md", "RELEASE.md"):
        src = ROOT / "docs" / name
        if src.is_file():
            shutil.copy2(src, out / name)

    manifest = {
        "surface": SURFACE_WEB,
        "version": __version__,
        "generated_at": _utc(),
        "focus": WEB_FOCUS,
        "paths": {
            "index": "index.html",
            "demo_site": "demos/site_maintenance/index.html",
        },
        "github_pages_optional": True,
        "local_command": "python -m mainframe surfaces build-web",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return {
        "ok": True,
        "surface": SURFACE_WEB,
        "dest": str(out),
        "index": str(out / "index.html"),
        "manifest": manifest,
        "hosted_pages_required": False,
    }
