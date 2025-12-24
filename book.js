(() => {
  const KEY = "readerState.v2";

  function loadState() {
    try { return JSON.parse(localStorage.getItem(KEY) || "{}"); }
    catch { return {}; }
  }

  const state = loadState();

  // Ensure shape
  state.pos ??= {};                 // per-page scroll positions
  state.lastReadingPageId ??= null; // last chapter page id

  function persist() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch {}
  }

  function saveScroll(pageId, y) {
    state.pos[pageId] = y;
    state.ts = Date.now();
    persist();
  }

  // Heuristic: treat pages with prev/next links as “reading pages”
  function isReadingPage() {
    return !!document.querySelector('a[data-nav="next"], a[data-nav="prev"]');
  }

  const pageId = document.documentElement.dataset.pageId || "";
  const reading = isReadingPage();

  // Remember scroll position (always), and remember “last reading page” (chapters only).
  if (pageId) {
    const onScroll = (() => {
      let t = null;
      return () => {
        if (t) return;
        t = setTimeout(() => {
          t = null;
          saveScroll(pageId, window.scrollY || 0);
          if (reading) {
            state.lastReadingPageId = pageId;
            persist();
          }
        }, 200);
      };
    })();
    window.addEventListener("scroll", onScroll, { passive: true });

    // Restore scroll position for chapters when returning to *that same* chapter.
    window.addEventListener("load", () => {
      if (!reading) return;
      if (state.lastReadingPageId !== pageId) return;

      const want = state.pos?.[pageId] ?? 0;
      if (want > 20) {
        window.scrollTo({ top: want, left: 0, behavior: "auto" });
      }
    });
  }

  // Smooth “page” scrolling
  function pageScroll(dir) {
    const vh = window.innerHeight || 800;
    const delta = Math.floor(vh * 0.88) * dir;
    window.scrollBy({ top: delta, left: 0, behavior: "smooth" });
  }

  // Keyboard controls (don’t steal Cmd/Ctrl/Alt shortcuts)
  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    const tag = (document.activeElement?.tagName || "").toLowerCase();
    const typing = tag === "input" || tag === "textarea" || tag === "select" || document.activeElement?.isContentEditable;
    if (typing) return;

    const next = document.querySelector('a[data-nav="next"]');
    const prev = document.querySelector('a[data-nav="prev"]');
    const toc  = document.querySelector('a[data-nav="toc"]');

    if (e.key === " " || e.key === "PageDown") {
      e.preventDefault();
      pageScroll(e.shiftKey ? -1 : 1);
      return;
    }
    if (e.key === "PageUp") {
      e.preventDefault();
      pageScroll(-1);
      return;
    }
    if (e.key.toLowerCase() === "n" && next) { e.preventDefault(); next.click(); return; }
    if (e.key.toLowerCase() === "p" && prev) { e.preventDefault(); prev.click(); return; }
    if (e.key.toLowerCase() === "t" && toc)  { e.preventDefault(); toc.click(); return; }
  });

  // Buttons
  document.querySelectorAll("[data-action='pagedown']").forEach(btn => btn.addEventListener("click", () => pageScroll(1)));
  document.querySelectorAll("[data-action='pageup']").forEach(btn => btn.addEventListener("click", () => pageScroll(-1)));

  // Resume reading (uses lastReadingPageId, not the current pageId)
  document.querySelectorAll("[data-action='resume']").forEach(btn => {
    const last = state.lastReadingPageId;
    if (!last) btn.setAttribute("disabled", "disabled");
  
    btn.addEventListener("click", () => {
      const id = state.lastReadingPageId;
      if (!id) return;
  
      // If we're on the TOC page, click the existing link (nice and simple)
      const a = document.querySelector(`a[data-page-id="${CSS.escape(id)}"]`);
      if (a) { a.click(); return; }
  
      // Otherwise, navigate directly (works from index.html too)
      const href = new URL(`./${id}.html`, document.baseURI).toString();
      window.location.href = href;
    });
  });

  // Primary read button (on index/home page)
  window.addEventListener("DOMContentLoaded", () => {
    const primary = document.querySelector('[data-action="primary-read"]');
    if (!primary) return;
  
    const defaultHref = primary.getAttribute("data-default-href") || "./toc.html";
    const last = state.lastReadingPageId;
  
    if (last) {
      primary.textContent = "Continue reading →";
      primary.setAttribute("href", `./${last}.html`);
      primary.setAttribute("title", "Continue where you left off");
    } else {
      primary.textContent = "Start reading →";
      primary.setAttribute("href", defaultHref);
      primary.removeAttribute("title");
    }
  });

  // Font picker
  const FONT_KEY = "readerFont.v1";

  function applyFont(v){
    document.documentElement.dataset.font = v;
    try { localStorage.setItem(FONT_KEY, v); } catch {}
  }

  window.addEventListener("DOMContentLoaded", () => {
    const saved = (() => { try { return localStorage.getItem(FONT_KEY); } catch { return null; } })();
    if (saved === "serif" || saved === "sans") applyFont(saved);
  
    const picker = document.getElementById("font-picker");
    if (!picker) return;
  
    picker.value = document.documentElement.dataset.font || "sans";
    picker.addEventListener("change", () => applyFont(picker.value));

    const cover = document.querySelector(".cover[data-cover-note]");
    if (!cover) return;

    const btn = cover.querySelector(".cover-info");
    const note = cover.querySelector("#cover-note");
    if (!btn || !note) return;

    const text = cover.getAttribute("data-cover-note") || "";
    note.textContent = text;

    btn.addEventListener("click", () => {
        const open = !note.hasAttribute("hidden");
        if (open) {
        note.setAttribute("hidden", "");
        btn.setAttribute("aria-expanded", "false");
        } else {
        note.removeAttribute("hidden");
        btn.setAttribute("aria-expanded", "true");
        }
    });

  });

  // Tap-to-scroll: Quick tap on content area scrolls down
  (() => {
    let touchStartTime = 0;
    let touchStartX = 0;
    let touchStartY = 0;
    let hasMoved = false;

    const LONG_PRESS_MS = 500;  // Longer than this = long press, ignore
    const MOVE_THRESHOLD = 10;   // Movement beyond this = drag, ignore

    document.addEventListener("touchstart", (e) => {
      // Ignore if touching interactive elements
      const target = e.target;
      if (target.tagName === "A" || target.tagName === "BUTTON" ||
          target.tagName === "INPUT" || target.tagName === "SELECT" ||
          target.closest("button") || target.closest("a")) {
        return;
      }

      touchStartTime = Date.now();
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
      hasMoved = false;
    }, { passive: true });

    document.addEventListener("touchmove", (e) => {
      if (touchStartTime === 0) return;

      const deltaX = Math.abs(e.touches[0].clientX - touchStartX);
      const deltaY = Math.abs(e.touches[0].clientY - touchStartY);

      if (deltaX > MOVE_THRESHOLD || deltaY > MOVE_THRESHOLD) {
        hasMoved = true;
      }
    }, { passive: true });

    document.addEventListener("touchend", (e) => {
      if (touchStartTime === 0) return;

      const touchDuration = Date.now() - touchStartTime;
      touchStartTime = 0;

      // Ignore if it was a long press or a drag
      if (touchDuration > LONG_PRESS_MS || hasMoved) {
        return;
      }

      // Ignore if touching interactive elements
      const target = e.target;
      if (target.tagName === "A" || target.tagName === "BUTTON" ||
          target.tagName === "INPUT" || target.tagName === "SELECT" ||
          target.closest("button") || target.closest("a")) {
        return;
      }

      // Quick tap detected! Scroll down one page
      e.preventDefault();
      pageScroll(1);
    });

    document.addEventListener("touchcancel", () => {
      touchStartTime = 0;
      hasMoved = false;
    }, { passive: true });
  })();

})();
