#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
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
    lastmod: datetime

# ---------- Templating ----------

CSS_PATH = Path(__file__).parent / "book.css"
CSS = CSS_PATH.read_text(encoding="utf-8") if CSS_PATH.exists() else ""

JS_PATH = Path(__file__).parent / "book.js"
JS = JS_PATH.read_text(encoding="utf-8") if JS_PATH.exists() else ""

def html_page(*, site_title: str, page_title: str, page_id: str, content_html: str, nav_html: str,
              author: str = "", description: str = "", base_url: str = "",
              favicon_href: str | None = None, lang: str = "en",
              og_image: str | None = None) -> str:
    full_title = f"{page_title} · {site_title}" if page_title else site_title

    # Build meta tags
    meta_tags = []
    if description:
        meta_tags.append(f'  <meta name="description" content="{html.escape(description)}" />')
    if author:
        meta_tags.append(f'  <meta name="author" content="{html.escape(author)}" />')

    # Open Graph tags
    if base_url:
        canonical_url = base_url.rstrip('/') + '/' + ('' if page_id == 'home' else f'{page_id}.html' if page_id != 'toc' else 'toc.html')
        meta_tags.append(f'  <link rel="canonical" href="{html.escape(canonical_url)}" />')
        meta_tags.append(f'  <meta property="og:url" content="{html.escape(canonical_url)}" />')

    meta_tags.append(f'  <meta property="og:title" content="{html.escape(full_title)}" />')
    meta_tags.append(f'  <meta property="og:type" content="website" />')
    if description:
        meta_tags.append(f'  <meta property="og:description" content="{html.escape(description)}" />')
    if og_image and base_url:
        img_url = base_url.rstrip('/') + '/' + og_image
        meta_tags.append(f'  <meta property="og:image" content="{html.escape(img_url)}" />')

    # Twitter Card tags
    meta_tags.append(f'  <meta name="twitter:card" content="summary" />')
    meta_tags.append(f'  <meta name="twitter:title" content="{html.escape(full_title)}" />')
    if description:
        meta_tags.append(f'  <meta name="twitter:description" content="{html.escape(description)}" />')
    if og_image and base_url:
        img_url = base_url.rstrip('/') + '/' + og_image
        meta_tags.append(f'  <meta name="twitter:image" content="{html.escape(img_url)}" />')

    # Favicon
    favicon_tag = ""
    if favicon_href:
        favicon_tag = f'  <link rel="icon" href="./{html.escape(favicon_href)}" />\n  <link rel="apple-touch-icon" href="./{html.escape(favicon_href)}" />'

    # Manifest
    manifest_tag = '  <link rel="manifest" href="./manifest.json" />'

    meta_html = "\n".join(meta_tags) if meta_tags else ""

    return f"""<!doctype html>
<html lang="{html.escape(lang)}" data-page-id="{html.escape(page_id)}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(full_title)}</title>
{meta_html}
{favicon_tag}
{manifest_tag}
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
        <select id="font-picker" title="Font">
        <option value="serif">Serif</option>
        <option value="sans">Sans</option>
        </select>
        <a class="btn" data-nav="toc" href="./toc.html" title="Table of contents (t)">TOC</a>
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
        src_mtime = datetime.fromtimestamp(src.stat().st_mtime, tz=timezone.utc)
        chapters.append(Chapter(i, title, src, slug, out_name, src_mtime))
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

def copy_epub(cfg: dict, root: Path, out_dir: Path) -> str | None:
    """
    Copy the EPUB file to assets if configured, return relative path.
    """
    epub = cfg.get("epub_file")
    if not epub:
        return None
    src = root / str(epub)
    if not src.exists():
        raise FileNotFoundError(f"epub_file not found: {src}")
    out_assets = out_dir / "assets"
    out_assets.mkdir(parents=True, exist_ok=True)
    dst = out_assets / src.name
    shutil.copy2(src, dst)
    return f"assets/{dst.name}"

def copy_favicon(cfg: dict, root: Path, out_dir: Path) -> str | None:
    """
    Copy the favicon file to output if configured, return relative path.
    """
    favicon = cfg.get("favicon")
    if not favicon:
        return None
    src = root / str(favicon)
    if not src.exists():
        raise FileNotFoundError(f"favicon not found: {src}")
    dst = out_dir / src.name
    shutil.copy2(src, dst)
    return src.name

def build_extra_links(cfg: dict, epub_href: str | None) -> str:
    """
    Build HTML for extra download/external links on the index page.
    """
    links_html = []

    # EPUB download button
    if epub_href:
        links_html.append(f'<a class="btn" href="./{html.escape(epub_href)}" download>Download EPUB</a>')

    # External links from config
    external_links = cfg.get("external_link", [])
    for link in external_links:
        text = str(link.get("text", "External Link"))
        url = str(link.get("url", ""))
        if url:
            links_html.append(f'<a class="btn" href="{html.escape(url)}" rel="noopener">{html.escape(text)}</a>')

    return "\n    ".join(links_html)

def generate_sitemap(cfg: dict, chapters: list[Chapter]) -> str:
    """
    Generate sitemap.xml for SEO.
    """
    base_url_raw = str(cfg.get("base_url", "")).strip()
    if not base_url_raw:
        return ""  # Skip sitemap if no base_url configured
    base_url = base_url_raw.rstrip('/')
    changefreq = str(cfg.get("sitemap_changefreq", "monthly")).strip().lower()

    def format_datetime(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d")
    lastmod = format_datetime(datetime.now(timezone.utc))

    urls = []
    # Home page
    urls.append(f"""  <url>
    <loc>{html.escape(base_url)}/</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>{changefreq}</changefreq>
    <priority>1.0</priority>
  </url>""")

    # TOC page
    urls.append(f"""  <url>
    <loc>{html.escape(base_url)}/toc.html</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>{changefreq}</changefreq>
    <priority>0.9</priority>
  </url>""")

    # Chapter pages
    for ch in chapters:
        urls.append(f"""  <url>
    <loc>{html.escape(base_url)}/{html.escape(ch.out_name)}</loc>
    <lastmod>{format_datetime(ch.lastmod)}</lastmod>
    <changefreq>{changefreq}</changefreq>
    <priority>0.8</priority>
  </url>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>
"""

def generate_rss(cfg: dict, chapters: list[Chapter]) -> str:
    """
    Generate RSS feed for the book.
    """
    base_url_raw = str(cfg.get("base_url", "")).strip()
    if not base_url_raw:
        return ""  # Skip RSS if no base_url configured
    base_url = base_url_raw.rstrip('/')

    site_title = str(cfg.get("title", "Untitled Book"))
    author = str(cfg.get("author", "")).strip()
    description = str(cfg.get("description", f"Read {site_title} online")).strip()
    lang = str(cfg.get("language", "en")).strip()

    pub_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    items = []
    for ch in chapters:
        items.append(f"""    <item>
      <title>{html.escape(ch.title)}</title>
      <link>{html.escape(base_url)}/{html.escape(ch.out_name)}</link>
      <guid>{html.escape(base_url)}/{html.escape(ch.out_name)}</guid>
      <description>{html.escape(ch.title)}</description>
      <pubDate>{pub_date}</pubDate>
    </item>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{html.escape(site_title)}</title>
    <link>{html.escape(base_url)}/</link>
    <description>{html.escape(description)}</description>
    <language>{html.escape(lang)}</language>
    <pubDate>{pub_date}</pubDate>
    <atom:link href="{html.escape(base_url)}/feed.xml" rel="self" type="application/rss+xml" />
{chr(10).join(items)}
  </channel>
</rss>
"""

def generate_robots_txt(cfg: dict) -> str:
    """
    Generate robots.txt. Can be overridden via robots_txt config option.
    """
    custom = cfg.get("robots_txt")
    if custom:
        return str(custom)

    base_url = str(cfg.get("base_url", "")).rstrip('/')
    sitemap_line = f"\nSitemap: {base_url}/sitemap.xml" if base_url else ""

    return f"""User-agent: *
Allow: /{sitemap_line}
"""

def generate_manifest(cfg: dict, favicon_href: str | None) -> str:
    """
    Generate manifest.json for PWA support.
    """
    site_title = str(cfg.get("title", "Untitled Book"))
    description = str(cfg.get("description", f"Read {site_title} online")).strip()

    icons = []
    if favicon_href:
        # Assume it's a reasonable size for now
        icons.append({
            "src": favicon_href,
            "sizes": "any",
            "type": "image/png"
        })

    import json
    manifest = {
        "name": site_title,
        "short_name": site_title[:12] if len(site_title) > 12 else site_title,
        "description": description,
        "start_url": "./index.html",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#000000",
        "icons": icons
    }

    return json.dumps(manifest, indent=2)

def build_site(toml_path: Path, out_dir: Path) -> None:
    root = toml_path.parent.resolve()
    cfg = load_config(toml_path)

    site_title = str(cfg.get("title", "Untitled Book"))
    author = str(cfg.get("author", "")).strip()
    lang = str(cfg.get("language", "en")).strip()
    description = str(cfg.get("description", f"Read {site_title} online")).strip()
    base_url = str(cfg.get("base_url", "")).rstrip('/')

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cover_href = copy_cover(cfg, root, out_dir)
    cover_alt = str(cfg.get("cover_alt", "Cover image"))
    cover_title = str(cfg.get("cover_title", "")).strip()

    epub_href = copy_epub(cfg, root, out_dir)
    favicon_href = copy_favicon(cfg, root, out_dir)

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
        nav_html="",
        author=author,
        description=description,
        base_url=base_url,
        favicon_href=favicon_href,
        lang=lang,
        og_image=cover_href
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
    extra_links = build_extra_links(cfg, epub_href)
    extra_links_html = f"\n    {extra_links}" if extra_links else ""

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
    <a class="btn" href="./toc.html">Table of contents</a>{extra_links_html}
  </p>
</div>
"""
    write_text(out_dir / "index.html", html_page(
        site_title=site_title,
        page_title="Home",
        page_id="home",
        content_html=index_content,
        nav_html="",
        author=author,
        description=description,
        base_url=base_url,
        favicon_href=favicon_href,
        lang=lang,
        og_image=cover_href
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
            nav_html=chapter_nav(prev_href, next_href),
            author=author,
            description=f"{ch.title} - {description}",
            base_url=base_url,
            favicon_href=favicon_href,
            lang=lang,
            og_image=cover_href
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
        nav_html="",
        author=author,
        description=description,
        base_url=base_url,
        favicon_href=favicon_href,
        lang=lang,
        og_image=cover_href
    ))

    # Generate sitemap.xml
    sitemap_xml = generate_sitemap(cfg, chapters)
    if sitemap_xml:
        write_text(out_dir / "sitemap.xml", sitemap_xml)

    # Generate RSS feed
    rss_xml = generate_rss(cfg, chapters)
    if rss_xml:
        write_text(out_dir / "feed.xml", rss_xml)

    # Generate robots.txt
    robots_txt = generate_robots_txt(cfg)
    write_text(out_dir / "robots.txt", robots_txt)

    # Generate manifest.json
    manifest_json = generate_manifest(cfg, favicon_href)
    write_text(out_dir / "manifest.json", manifest_json)

    # Write a tiny "how to host" helper (optional, but nice)
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
