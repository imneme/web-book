#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    import tomllib  # py3.11+
except Exception:  # pragma: no cover
    print("Python 3.11+ required (tomllib).", file=sys.stderr)
    raise

# ---------- Utilities ----------

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def write_text(path: Path, s: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s, encoding="utf-8")

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    s = re.sub(r"^-+|-+$", "", s)
    return s or "chapter"

def extract_body_inner(html_text: str) -> str:
    """
    If a full HTML document is provided, extract what's inside <body>.
    Otherwise return the input as-is.
    """
    m = re.search(r"<body\b[^>]*>(.*)</body\s*>", html_text, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    return html_text.strip()

def render_markdown(md_text: str) -> str:
    """
    Optional dependency: 'markdown' (pip install markdown).
    If unavailable, fail with a helpful message.
    """
    try:
        import markdown  # type: ignore
    except Exception:
        raise RuntimeError(
            "Markdown input detected, but the 'markdown' package isn't installed.\n"
            "Install it with: pip install markdown\n"
            "Or convert that chapter to HTML."
        )
    # Reasonable defaults; you can add more extensions later.
    return markdown.markdown(md_text, extensions=["extra", "sane_lists", "smarty"])

# ---------- Data model ----------

@dataclass(frozen=True)
class Chapter:
    index: int
    title: str
    source: Path
    slug: str
    out_name: str  # file name in output, e.g. "chapter-1-the-awkward.html"

# ---------- Templating ----------

CSS_PATH = Path(__file__).parent / "book.css"
CSS = CSS_PATH.read_text(encoding="utf-8") if CSS_PATH.exists() else ""

JS_PATH = Path(__file__).parent / "book.js"
JS = JS_PATH.read_text(encoding="utf-8") if JS_PATH.exists() else ""

def html_page(*, site_title: str, page_title: str, page_id: str, content_html: str, nav_html: str) -> str:
    full_title = f"{page_title} · {site_title}" if page_title else site_title
    return f"""<!doctype html>
<html lang="en" data-page-id="{html.escape(page_id)}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(full_title)}</title>
  <style>{CSS}</style>
</head>
<body>
  <header class="sitebar">
    <div class="sitebar-inner">
      <div class="brand"><a href="./index.html">{html.escape(site_title)}</a>
      <span class="brand-where">{html.escape(page_title)}</span>
      </div>
      <div class="spacer"></div>
      <div class="navbtns">
        <a class="btn" data-nav="toc" href="./toc.html" title="Table of contents (t)">TOC</a>
        <select id="font-picker" title="Font">
        <option value="serif">Serif</option>
        <option value="sans">Sans</option>
        </select>
        <button type="button" data-action="pageup" title="Page up (PageUp or Shift+Space)">▲</button>
        <button type="button" data-action="pagedown" title="Page down (Space / PageDown)">▼</button>
      </div>
    </div>
  </header>

  <main>
    <article class="reader" data-page-id="{html.escape(page_id)}">
      {content_html}
    </article>
    {nav_html}
  </main>

  <script>{JS}</script>
</body>
</html>
"""

def chapter_nav(prev_href: str | None, next_href: str | None) -> str:
    left = f'<a data-nav="prev" href="{html.escape(prev_href)}">← Prev</a>' if prev_href else '<span></span>'
    right = f'<a data-nav="next" href="{html.escape(next_href)}">Next →</a>' if next_href else '<span></span>'
    return f"""
<div class="footer-nav">
  {left}
  {right}
</div>
<p class="smallnote">Keyboard: <kbd>Space</kbd> page down, <kbd>Shift</kbd>+<kbd>Space</kbd> page up, <kbd>n</kbd>/<kbd>p</kbd> next/prev chapter, <kbd>t</kbd> TOC.</p>
"""

# ---------- Build steps ----------

def load_config(toml_path: Path) -> dict:
    data = tomllib.loads(read_text(toml_path))
    if "chapter" not in data or not isinstance(data["chapter"], list) or not data["chapter"]:
        raise ValueError("book.toml must include at least one [[chapter]] entry.")
    return data

def load_optional_frontpage(root: Path) -> str:
    """
    Looks for src/frontpage.(md|html) and returns HTML (or empty string).
    """
    md = root / "src" / "frontpage.md"
    htmlp = root / "src" / "frontpage.html"

    if htmlp.exists():
        return extract_body_inner(read_text(htmlp))
    if md.exists():
        return render_markdown(read_text(md))
    return ""

def build_chapters(cfg: dict, root: Path, out_dir: Path) -> list[Chapter]:
    chapters = []
    for i, ch in enumerate(cfg["chapter"], start=1):
        title = str(ch.get("title", f"Chapter {i}"))
        src = root / str(ch["source"])
        if not src.exists():
            raise FileNotFoundError(f"Chapter source not found: {src}")
        slug = slugify(f"{i:02d}-{title}")
        out_name = f"{slug}.html"
        chapters.append(Chapter(i, title, src, slug, out_name))
    return chapters

def chapter_content_html(ch: Chapter) -> str:
    ext = ch.source.suffix.lower()
    raw = read_text(ch.source)
    if ext in (".html", ".htm", ".xhtml"):
        inner = extract_body_inner(raw)
    elif ext in (".md", ".markdown"):
        inner = render_markdown(raw)
    else:
        # Fallback: treat as plain text
        inner = "<pre>" + html.escape(raw) + "</pre>"
    
    # Does the text already have a top-level heading?
    if re.search(r"<h1\b[^>]*>.*?</h1\s*>", inner, re.IGNORECASE | re.DOTALL):
        return inner
    else:
        return f"<h1>{html.escape(ch.title)}</h1>\n" + inner

def copy_cover(cfg: dict, root: Path, out_dir: Path) -> str | None:
    cover = cfg.get("cover_image")
    if not cover:
        return None
    src = root / str(cover)
    if not src.exists():
        raise FileNotFoundError(f"cover_image not found: {src}")
    out_assets = out_dir / "assets"
    out_assets.mkdir(parents=True, exist_ok=True)
    dst = out_assets / src.name
    shutil.copy2(src, dst)
    return f"assets/{dst.name}"

def build_site(toml_path: Path, out_dir: Path) -> None:
    root = toml_path.parent.resolve()
    cfg = load_config(toml_path)

    site_title = str(cfg.get("title", "Untitled Book"))
    author = str(cfg.get("author", "")).strip()
    lang = str(cfg.get("language", "en")).strip()

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cover_href = copy_cover(cfg, root, out_dir)
    cover_alt = str(cfg.get("cover_alt", "Cover image"))
    cover_title = str(cfg.get("cover_title", "")).strip()

    chapters = build_chapters(cfg, root, out_dir)

    # TOC page
    toc_items = "\n".join(
        f'<li><a data-page-id="{html.escape(ch.slug)}" href="./{html.escape(ch.out_name)}">{html.escape(ch.title)}</a></li>'
        for ch in chapters
    )
    toc_content = f"""
<h1>{html.escape(site_title)}</h1>
<div class="meta">{html.escape(author) if author else ""}</div>
<div class="toc">
  <p class="smallnote">Tip: hit <kbd>t</kbd> any time for TOC. Resume works if your browser allows localStorage.</p>
  <button type="button" data-action="resume">Resume reading</button>
  <hr/>
  <ul>
    {toc_items}
  </ul>
</div>
"""
    write_text(out_dir / "toc.html", html_page(
        site_title=site_title,
        page_title="Table of contents",
        page_id="toc",
        content_html=toc_content,
        nav_html=""
    ))

    # Index page (cover + quick links)
    cover_alt = str(cfg.get("cover_alt", "Book cover image"))
    cover_note = str(cfg.get("cover_title", "")).strip()  # same text for hover + click

    cover_html = ""
    if cover_href:
        title_attr = f' title="{html.escape(cover_note)}"' if cover_note else ""
        note_attr = f' data-cover-note="{html.escape(cover_note)}"' if cover_note else ""

        cover_html = f"""
<div class="cover"{note_attr}>
  <img src="./{html.escape(cover_href)}"
       alt="{html.escape(cover_alt)}"{title_attr}>
  {'<button class="cover-info" type="button" aria-expanded="false" aria-controls="cover-note">ⓘ</button>' if cover_note else ''}
  {'<div id="cover-note" class="cover-note" hidden></div>' if cover_note else ''}
</div>
"""

    first = chapters[0]
    front_html = load_optional_frontpage(root)

    primary_href = f"./{first.out_name}"
    index_content = f"""
<h1>{html.escape(site_title)}</h1>
<div class="meta">{html.escape(author) if author else ""}</div>

{cover_html}

<div class="frontmatter">
  {front_html if front_html else ""}
</div>

<div class="toc" style="margin-top:18px;">
  <p class="front-actions">
    <a class="btn btn-primary"
       data-action="primary-read"
       data-default-href="{html.escape(primary_href)}"
       href="{html.escape(primary_href)}">
      Start reading →
    </a>
    <a class="btn" href="./toc.html">Table of contents</a>
    <a class="btn" href="./Phoenix.epub" download>Download EPUB</a>
    <a class="btn" href="YOUR_AO3_URL_HERE" rel="noopener">Read on AO3</a>
  </p>
</div>
"""
    write_text(out_dir / "index.html", html_page(
        site_title=site_title,
        page_title="Home",
        page_id="home",
        content_html=index_content,
        nav_html=""
    ))

    # Chapters
    for idx, ch in enumerate(chapters):
        prev_href = f"./{chapters[idx-1].out_name}" if idx > 0 else None
        next_href = f"./{chapters[idx+1].out_name}" if idx + 1 < len(chapters) else None
        content = chapter_content_html(ch)

        write_text(out_dir / ch.out_name, html_page(
            site_title=site_title,
            page_title=ch.title,
            page_id=ch.slug,
            content_html=content,
            nav_html=chapter_nav(prev_href, next_href)
        ))

    # Small redirect for convenience
    write_text(out_dir / "404.html", html_page(
        site_title=site_title,
        page_title="Not found",
        page_id="404",
        content_html=f"""
<h1>Not found</h1>
<p>Try the <a href="./toc.html">table of contents</a>.</p>
""",
        nav_html=""
    ))

    # Write a tiny “how to host” helper (optional, but nice)
    write_text(out_dir / "README.txt",
               "Upload this folder to any static host.\n"
               "- GitHub Pages: push contents to /docs or gh-pages.\n"
               "- Netlify: drag-drop the folder.\n"
               "- Local test: python -m http.server in this folder.\n")

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Build a simple online reader from book.toml + HTML/Markdown chapters.")
    ap.add_argument("toml", type=Path, help="Path to book.toml")
    ap.add_argument("-o", "--out", type=Path, default=Path("dist"), help="Output directory (default: dist)")
    args = ap.parse_args(argv)

    try:
        build_site(args.toml, args.out)
    except Exception as e:
        print(f"Build failed: {e}", file=sys.stderr)
        return 1

    python_cmd = os.path.basename(sys.executable)
    print(f"Built site into: {args.out.resolve()}")
    print(f"Test locally: cd {args.out} && {python_cmd} -m http.server 8000")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
