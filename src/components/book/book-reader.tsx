import { useState, useCallback, useEffect, useRef } from "react";
import {
  BookOpen,
  BookmarkPlus,
  BookmarkMinus,
  ChevronLeft,
  ChevronRight,
  List,
  Settings2,
  Clock,
  Check,
  X,
  Bookmark as BookmarkIcon,
} from "lucide-react";
import { cn } from "../../lib/utils";
import { PARTS } from "../../lib/book/content";
import type { BookChapter, ReaderPreferences, ReadingProgress, Bookmark } from "../../lib/book/types";
import { DEFAULT_READER_PREFS } from "../../lib/book/types";
import { ContentBlockRenderer } from "./content-blocks";
import { PathSelector } from "./path-selector";
import { PathProgress } from "./path-progress";
import { getReadingPath, getNextPathChapter, isChapterInPath } from "../../lib/book/reading-paths";

const PREFS_KEY = "ainative-book-prefs";
const PROGRESS_KEY = "ainative-book-progress";
const BOOKMARKS_KEY = "ainative-book-bookmarks";

function getSiteTheme(): ReaderPreferences["theme"] {
  if (typeof window === "undefined") return "light";
  const siteTheme = document.documentElement.getAttribute("data-theme");
  return siteTheme === "dark" ? "dark" : "light";
}

function loadPrefs(): ReaderPreferences {
  if (typeof window === "undefined") return DEFAULT_READER_PREFS;
  try {
    const saved = localStorage.getItem(PREFS_KEY);
    if (saved) return { ...DEFAULT_READER_PREFS, ...JSON.parse(saved) };
    // No saved prefs — match the site theme
    return { ...DEFAULT_READER_PREFS, theme: getSiteTheme() };
  } catch {
    return DEFAULT_READER_PREFS;
  }
}

function savePrefs(prefs: ReaderPreferences) {
  localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
}

function loadProgress(): Record<string, ReadingProgress> {
  if (typeof window === "undefined") return {};
  try {
    const saved = localStorage.getItem(PROGRESS_KEY);
    return saved ? JSON.parse(saved) : {};
  } catch {
    return {};
  }
}

function saveProgress(progress: Record<string, ReadingProgress>) {
  localStorage.setItem(PROGRESS_KEY, JSON.stringify(progress));
}

function loadBookmarks(): Bookmark[] {
  if (typeof window === "undefined") return [];
  try {
    const saved = localStorage.getItem(BOOKMARKS_KEY);
    return saved ? JSON.parse(saved) : [];
  } catch {
    return [];
  }
}

function saveBookmarks(bookmarks: Bookmark[]) {
  localStorage.setItem(BOOKMARKS_KEY, JSON.stringify(bookmarks));
}

/* ─── SlidePanel (replaces shadcn Sheet) ─── */

function SlidePanel({
  open,
  onClose,
  side,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  side: "left" | "right";
  title: string;
  children: React.ReactNode;
}) {
  const translateValue = open
    ? "translateX(0)"
    : side === "left"
      ? "translateX(-100%)"
      : "translateX(100%)";

  return (
    <>
      <div
        className={cn(
          "fixed inset-0 bg-black/40 z-40",
          open ? "" : "pointer-events-none"
        )}
        style={{
          opacity: open ? 1 : 0,
          transition: "opacity 350ms cubic-bezier(0.4, 0, 0.2, 1)",
        }}
        onClick={onClose}
      />
      <div
        className={cn(
          "fixed top-0 z-50 h-full w-80 bg-surface border-border overflow-y-auto",
          side === "left" ? "left-0 border-r" : "right-0 border-l",
        )}
        style={{
          transform: translateValue,
          transition: "transform 350ms cubic-bezier(0.4, 0, 0.2, 1)",
          willChange: "transform",
        }}
      >
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            {side === "left" && <BookOpen className="h-4 w-4" />}
            {title}
          </h2>
          <button
            onClick={onClose}
            className="h-8 w-8 flex items-center justify-center rounded-md hover:bg-surface-raised transition-colors cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </>
  );
}

/* ─── BookReader ─── */

export function BookReader({
  chapters: CHAPTERS,
  initialChapterId,
}: {
  chapters: BookChapter[];
  initialChapterId?: string;
}) {
  const initialChapter = initialChapterId
    ? CHAPTERS.find((ch) => ch.id === initialChapterId) ?? CHAPTERS[0]
    : CHAPTERS[0];

  const [currentChapter, setCurrentChapter] = useState<BookChapter>(initialChapter);
  const [prefs, setPrefs] = useState<ReaderPreferences>(DEFAULT_READER_PREFS);
  const [progress, setProgress] = useState<Record<string, ReadingProgress>>({});
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [tocOpen, setTocOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [tocTab, setTocTab] = useState<"chapters" | "bookmarks">("chapters");
  const [activePath, setActivePath] = useState<string | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  // Load state from localStorage on mount
  useEffect(() => {
    setPrefs(loadPrefs());
    setProgress(loadProgress());
    setBookmarks(loadBookmarks());
    const savedPath = localStorage.getItem("ainative-book-path");
    if (savedPath) setActivePath(savedPath);
  }, []);

  const handlePathChange = useCallback((pathId: string | null) => {
    setActivePath(pathId);
    if (pathId) {
      localStorage.setItem("ainative-book-path", pathId);
    } else {
      localStorage.removeItem("ainative-book-path");
    }
  }, []);

  // Track scroll progress
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;

    const handleScroll = () => {
      const scrollTop = el.scrollTop;
      const scrollHeight = el.scrollHeight - el.clientHeight;
      if (scrollHeight <= 0) return;
      const pct = Math.min(1, scrollTop / scrollHeight);

      setProgress((prev) => {
        const highWater = Math.max(pct, prev[currentChapter.id]?.progress ?? 0);
        const updated = {
          ...prev,
          [currentChapter.id]: {
            chapterId: currentChapter.id,
            progress: highWater,
            scrollPosition: scrollTop,
            lastReadAt: new Date().toISOString(),
          },
        };
        saveProgress(updated);
        return updated;
      });
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, [currentChapter.id]);

  const updatePrefs = useCallback((patch: Partial<ReaderPreferences>) => {
    setPrefs((prev) => {
      const next = { ...prev, ...patch };
      savePrefs(next);
      return next;
    });
  }, []);

  const goToChapter = useCallback(
    (chapter: BookChapter, scrollTo?: number) => {
      setCurrentChapter(chapter);
      setTocOpen(false);
      // Update URL without full reload
      const slug = `ch-${chapter.number}-${chapter.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/-+$/g, "")}`;
      window.history.replaceState({}, "", `/book/${slug}/`);
      if (scrollTo !== undefined && scrollTo > 0) {
        setTimeout(() => {
          contentRef.current?.scrollTo({ top: scrollTo, behavior: "smooth" });
        }, 100);
      } else {
        contentRef.current?.scrollTo({ top: 0, behavior: "smooth" });
      }
    },
    []
  );

  // Bookmark: add
  const addBookmark = useCallback(() => {
    const el = contentRef.current;
    if (!el) return;

    let nearestSection: { id: string; title: string } | null = null;
    for (const section of currentChapter.sections) {
      const sectionEl = document.getElementById(section.id);
      if (sectionEl) {
        const rect = sectionEl.getBoundingClientRect();
        const containerRect = el.getBoundingClientRect();
        if (rect.top <= containerRect.top + 200) {
          nearestSection = section;
        }
      }
    }

    const label = nearestSection
      ? `Ch. ${currentChapter.number}: ${nearestSection.title}`
      : `Ch. ${currentChapter.number}: ${currentChapter.title}`;

    const newBookmark: Bookmark = {
      id: crypto.randomUUID(),
      chapterId: currentChapter.id,
      sectionId: nearestSection?.id ?? null,
      scrollPosition: el.scrollTop,
      label,
      createdAt: new Date().toISOString(),
    };

    setBookmarks((prev) => {
      const updated = [...prev, newBookmark];
      saveBookmarks(updated);
      return updated;
    });
  }, [currentChapter]);

  // Bookmark: remove
  const removeBookmark = useCallback((id: string) => {
    setBookmarks((prev) => {
      const updated = prev.filter((b) => b.id !== id);
      saveBookmarks(updated);
      return updated;
    });
  }, []);

  // Navigate to bookmark
  const goToBookmark = useCallback(
    (bm: Bookmark) => {
      const chapter = CHAPTERS.find((ch) => ch.id === bm.chapterId);
      if (chapter) goToChapter(chapter, bm.scrollPosition);
    },
    [CHAPTERS, goToChapter]
  );

  const currentChapterBookmarks = bookmarks.filter((b) => b.chapterId === currentChapter.id);
  const currentIndex = CHAPTERS.findIndex((ch) => ch.id === currentChapter.id);

  // Path-aware navigation
  const prevChapter = (() => {
    if (!activePath) return currentIndex > 0 ? CHAPTERS[currentIndex - 1] : null;
    const path = getReadingPath(activePath);
    if (!path) return currentIndex > 0 ? CHAPTERS[currentIndex - 1] : null;
    const pathIdx = path.chapterIds.indexOf(currentChapter.id);
    if (pathIdx <= 0) return null;
    return CHAPTERS.find((ch) => ch.id === path.chapterIds[pathIdx - 1]) ?? null;
  })();

  const nextChapter = (() => {
    if (!activePath) return currentIndex < CHAPTERS.length - 1 ? CHAPTERS[currentIndex + 1] : null;
    const nextId = getNextPathChapter(activePath, currentChapter.id);
    if (!nextId) return null;
    return CHAPTERS.find((ch) => ch.id === nextId) ?? null;
  })();

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowLeft" && prevChapter) {
        e.preventDefault();
        goToChapter(prevChapter);
      } else if (e.key === "ArrowRight" && nextChapter) {
        e.preventDefault();
        goToChapter(nextChapter);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [prevChapter, nextChapter, goToChapter]);

  const chaptersByPart = (() => {
    const grouped = new Map<number, BookChapter[]>();
    for (const ch of CHAPTERS) {
      const part = ch.part.number;
      if (!grouped.has(part)) grouped.set(part, []);
      grouped.get(part)!.push(ch);
    }
    return grouped;
  })();

  const fontFamilyClass =
    prefs.fontFamily === "serif"
      ? "font-serif"
      : prefs.fontFamily === "mono"
        ? "font-mono"
        : "font-sans";

  const overallProgress =
    CHAPTERS.length > 0
      ? CHAPTERS.reduce((sum, ch) => sum + (progress[ch.id]?.progress ?? 0), 0) / CHAPTERS.length
      : 0;

  const completedChapters = CHAPTERS.filter((ch) => (progress[ch.id]?.progress ?? 0) >= 0.9).length;

  return (
    <div className="flex flex-col h-screen" data-book-theme={prefs.theme}>
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-border px-4 py-2 shrink-0 bg-surface">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setTocOpen(true)}
            className="h-8 w-8 flex items-center justify-center rounded-md hover:bg-surface-raised transition-colors cursor-pointer"
            title="Table of Contents"
          >
            <List className="h-4 w-4" />
          </button>
          <a
            href="/"
            className="text-xs text-text-muted hover:text-primary transition-colors no-underline hidden sm:inline-flex items-center gap-1.5"
            title="Back to ainative.business"
          >
            <img
              src="/ainative-s-64.png"
              alt="ainative.business"
              width="20"
              height="20"
              className="h-5 w-5 shrink-0"
            />
            <span className="hidden md:inline font-semibold tracking-tight">
              <span className="text-primary">ai</span><span className="text-text">native</span><span className="text-text-muted">.business</span>
            </span>
          </a>
          <span className="text-text-muted/30 hidden sm:inline">/</span>
          <a
            href="/book/"
            className="text-xs text-text-muted hover:text-primary transition-colors font-mono tracking-wide no-underline hidden sm:inline-flex items-center gap-1"
          >
            <BookOpen className="h-3.5 w-3.5" />
            <span className="hidden md:inline">AI Native Business</span>
          </a>
          <span className="text-border hidden sm:inline">|</span>
          <div className="hidden sm:block">
            <p className="text-sm font-medium">
              Ch. {currentChapter.number}: {currentChapter.title}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <span className="text-xs text-text-muted mr-2 hidden sm:inline-flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {currentChapter.readingTime} min
          </span>

          {activePath ? (
            <div className="hidden sm:flex mr-2">
              <PathProgress pathId={activePath} progress={progress} />
            </div>
          ) : (
            <div className="hidden sm:flex items-center gap-2 mr-2">
              <div className="w-20 h-1.5 rounded-full bg-surface-raised overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all"
                  style={{ width: `${overallProgress * 100}%` }}
                />
              </div>
              <span className="text-xs text-text-muted">
                {Math.round(overallProgress * 100)}%
              </span>
            </div>
          )}

          <button
            className="h-8 w-8 flex items-center justify-center rounded-md hover:bg-surface-raised transition-colors cursor-pointer"
            onClick={addBookmark}
            title="Bookmark this position"
          >
            {currentChapterBookmarks.length > 0 ? (
              <BookmarkIcon className="h-4 w-4 fill-primary text-primary" />
            ) : (
              <BookmarkPlus className="h-4 w-4" />
            )}
          </button>

          <button
            onClick={() => setSettingsOpen(true)}
            className="h-8 w-8 flex items-center justify-center rounded-md hover:bg-surface-raised transition-colors cursor-pointer"
          >
            <Settings2 className="h-4 w-4" />
          </button>
        </div>
      </header>

      {/* TOC Panel */}
      <SlidePanel open={tocOpen} onClose={() => setTocOpen(false)} side="left" title="Contents">
        <div className="px-4 pb-4 space-y-4">
          {/* Tab switcher */}
          <div className="flex gap-1 p-1 rounded-lg bg-surface-raised mt-4">
            <button
              onClick={() => setTocTab("chapters")}
              className={cn(
                "flex-1 text-xs font-medium py-1.5 rounded-md transition-colors cursor-pointer",
                tocTab === "chapters"
                  ? "bg-surface shadow-sm"
                  : "text-text-muted hover:text-text"
              )}
            >
              Chapters
            </button>
            <button
              onClick={() => setTocTab("bookmarks")}
              className={cn(
                "flex-1 text-xs font-medium py-1.5 rounded-md transition-colors cursor-pointer",
                tocTab === "bookmarks"
                  ? "bg-surface shadow-sm"
                  : "text-text-muted hover:text-text"
              )}
            >
              Bookmarks{bookmarks.length > 0 && ` (${bookmarks.length})`}
            </button>
          </div>

          {/* Overall progress */}
          {tocTab === "chapters" && (
            <div className="flex items-center gap-3 px-1">
              <div className="flex-1 h-1.5 rounded-full bg-surface-raised overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all"
                  style={{ width: `${overallProgress * 100}%` }}
                />
              </div>
              <span className="text-xs text-text-muted whitespace-nowrap">
                {completedChapters}/{CHAPTERS.length} complete
              </span>
            </div>
          )}

          {tocTab === "chapters" ? (
            <div className="space-y-6">
              <PathSelector activePath={activePath} onSelectPath={handlePathChange} />

              {PARTS.map((part) => (
                <div key={part.number}>
                  <p className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2">
                    Part {part.number}: {part.title}
                  </p>
                  <p className="text-xs text-text-muted mb-3">{part.description}</p>
                  <div className="space-y-1">
                    {(chaptersByPart.get(part.number) ?? []).map((ch) => {
                      const chProgress = progress[ch.id]?.progress ?? 0;
                      const chPct = Math.round(chProgress * 100);
                      const inPath = !activePath || isChapterInPath(activePath, ch.id);
                      return (
                        <button
                          key={ch.id}
                          onClick={() => goToChapter(ch)}
                          className={cn(
                            "w-full text-left px-3 py-2 rounded-lg text-sm transition-colors cursor-pointer",
                            ch.id === currentChapter.id
                              ? "bg-primary-dim text-primary font-medium"
                              : "hover:bg-surface-raised",
                            !inPath && "opacity-40"
                          )}
                        >
                          <div className="flex items-center justify-between">
                            <span>
                              {ch.number}. {ch.title}
                            </span>
                            <span className="flex items-center gap-1.5">
                              {!inPath && (
                                <span className="text-[10px] text-text-muted">Not in path</span>
                              )}
                              {chProgress >= 0.9 ? (
                                <Check className="h-3.5 w-3.5 text-success" />
                              ) : chProgress > 0 ? (
                                <span className="text-xs text-text-muted">{chPct}%</span>
                              ) : null}
                            </span>
                          </div>
                          <p className="text-xs text-text-muted mt-0.5 line-clamp-1">
                            {ch.subtitle}
                          </p>
                          {chProgress > 0 && chProgress < 0.9 && (
                            <div className="mt-1.5 h-1 rounded-full bg-surface-raised overflow-hidden">
                              <div
                                className="h-full bg-primary/40 rounded-full transition-all"
                                style={{ width: `${chPct}%` }}
                              />
                            </div>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-1">
              {bookmarks.length === 0 ? (
                <div className="text-center py-8">
                  <BookmarkIcon className="h-8 w-8 text-text-muted/40 mx-auto mb-2" />
                  <p className="text-sm text-text-muted">No bookmarks yet</p>
                  <p className="text-xs text-text-muted mt-1">
                    Use the bookmark button while reading to save your place
                  </p>
                </div>
              ) : (
                bookmarks.map((bm) => (
                  <div
                    key={bm.id}
                    className="flex items-start gap-2 px-3 py-2 rounded-lg hover:bg-surface-raised group"
                  >
                    <button
                      onClick={() => goToBookmark(bm)}
                      className="flex-1 text-left cursor-pointer"
                    >
                      <p className="text-sm font-medium">{bm.label}</p>
                      <p className="text-xs text-text-muted mt-0.5">
                        {new Date(bm.createdAt).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                          hour: "numeric",
                          minute: "2-digit",
                        })}
                      </p>
                    </button>
                    <button
                      onClick={() => removeBookmark(bm.id)}
                      className="opacity-0 group-hover:opacity-100 text-text-muted hover:text-red-500 transition-all cursor-pointer p-1"
                      title="Remove bookmark"
                    >
                      <BookmarkMinus className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </SlidePanel>

      {/* Settings Panel */}
      <SlidePanel open={settingsOpen} onClose={() => setSettingsOpen(false)} side="right" title="Reading Settings">
        <div className="px-6 pb-6 space-y-6 mt-4">
          {/* Font size */}
          <div>
            <label className="text-sm font-medium mb-2 block">
              Font Size: {prefs.fontSize}px
            </label>
            <input
              type="range"
              value={prefs.fontSize}
              min={14}
              max={22}
              step={2}
              onChange={(e) => updatePrefs({ fontSize: Number(e.target.value) })}
              className="w-full accent-[var(--color-primary)]"
            />
            <div className="flex justify-between text-xs text-text-muted mt-1">
              <span>Small</span>
              <span>Large</span>
            </div>
          </div>

          {/* Line height */}
          <div>
            <label className="text-sm font-medium mb-2 block">
              Line Height: {prefs.lineHeight.toFixed(2)}
            </label>
            <input
              type="range"
              value={prefs.lineHeight * 100}
              min={150}
              max={200}
              step={5}
              onChange={(e) => updatePrefs({ lineHeight: Number(e.target.value) / 100 })}
              className="w-full accent-[var(--color-primary)]"
            />
            <div className="flex justify-between text-xs text-text-muted mt-1">
              <span>Compact</span>
              <span>Relaxed</span>
            </div>
          </div>

          {/* Font family */}
          <div>
            <label className="text-sm font-medium mb-3 block">Font</label>
            <div className="grid grid-cols-3 gap-2">
              {(["sans", "serif", "mono"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => updatePrefs({ fontFamily: f })}
                  className={cn(
                    "px-3 py-2 rounded-lg border text-sm capitalize transition-colors cursor-pointer",
                    prefs.fontFamily === f
                      ? "border-primary bg-primary-dim text-primary"
                      : "border-border hover:bg-surface-raised"
                  )}
                >
                  <span className={f === "serif" ? "font-serif" : f === "mono" ? "font-mono" : "font-sans"}>
                    {f}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Theme */}
          <div>
            <label className="text-sm font-medium mb-3 block">Reader Theme</label>
            <div className="grid grid-cols-3 gap-2">
              {(["light", "sepia", "dark"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => updatePrefs({ theme: t })}
                  className={cn(
                    "px-3 py-2 rounded-lg border text-sm capitalize transition-colors cursor-pointer",
                    prefs.theme === t
                      ? "border-primary bg-primary-dim text-primary"
                      : "border-border hover:bg-surface-raised"
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
        </div>
      </SlidePanel>

      {/* Reading area */}
      <div ref={contentRef} className="flex-1 overflow-y-auto book-reading-area">
        <article
          className={cn("mx-auto max-w-2xl px-6 py-10 sm:px-8 sm:py-14", fontFamilyClass)}
          style={{ fontSize: `${prefs.fontSize}px`, lineHeight: prefs.lineHeight }}
        >
          {/* Chapter header */}
          <header className="mb-12">
            <p className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2 font-mono">
              Part {currentChapter.part.number}: {currentChapter.part.title}
            </p>
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-3">
              Chapter {currentChapter.number}: {currentChapter.title}
            </h1>
            <p className="text-lg text-text-muted">{currentChapter.subtitle}</p>
            <p className="mt-2 font-mono text-xs text-text-muted/70 tracking-wide">
              by Manav Sehgal
            </p>
            <div className="flex items-center gap-4 mt-4 text-sm text-text-muted">
              <span className="inline-flex items-center gap-1">
                <Clock className="h-3.5 w-3.5" />
                {currentChapter.readingTime} min read
              </span>
              <span>
                {currentChapter.sections.length} section{currentChapter.sections.length !== 1 && "s"}
              </span>
              {(progress[currentChapter.id]?.progress ?? 0) > 0 && (
                <span>
                  {Math.round((progress[currentChapter.id]?.progress ?? 0) * 100)}% read
                </span>
              )}
            </div>
            <hr className="mt-8 border-border/50" />
          </header>

          {/* Sections */}
          {currentChapter.sections.length > 0 ? (
            currentChapter.sections.map((section) => (
              <section key={section.id} id={section.id} className="mb-12">
                <h2 className="text-2xl font-semibold tracking-tight mb-6">
                  {section.title}
                </h2>
                <div className="space-y-2">
                  {section.content.map((block, i) => (
                    <ContentBlockRenderer key={i} block={block} />
                  ))}
                </div>
              </section>
            ))
          ) : (
            <div className="text-center py-16 space-y-4">
              <BookOpen className="h-12 w-12 text-text-muted/30 mx-auto" />
              <h3 className="text-lg font-medium">This chapter is coming soon</h3>
              <p className="text-text-muted text-sm max-w-md mx-auto">
                Check back later for this content.
              </p>
            </div>
          )}

          {/* Chapter footer */}
          <footer className="mt-12 pt-6 border-t border-border/30 text-xs text-text-muted/60">
            Chapter {currentChapter.number} of {CHAPTERS.length}
          </footer>

          {/* Related docs links */}
          {currentChapter.relatedDocs && currentChapter.relatedDocs.length > 0 && (
            <div className="mt-8 p-6 rounded-lg bg-surface-raised border border-border">
              <h3 className="text-sm font-semibold mb-3">Explore Related Features</h3>
              <div className="flex flex-wrap gap-2">
                {currentChapter.relatedDocs.map((doc) => (
                  <a
                    key={doc}
                    href={`/docs/${doc}`}
                    className="text-xs px-3 py-1.5 rounded-md border border-border hover:bg-surface-overlay hover:text-primary transition-colors no-underline capitalize"
                  >
                    {doc.replace(/-/g, " ")}
                  </a>
                ))}
              </div>
            </div>
          )}

          {/* Chapter navigation */}
          <nav className="flex items-center justify-between border-t border-border/50 pt-8 mt-16">
            {prevChapter ? (
              <button
                onClick={() => goToChapter(prevChapter)}
                className="flex items-center gap-2 text-sm text-text-muted hover:text-text transition-colors cursor-pointer rounded-lg px-3 py-2 -mx-3"
              >
                <ChevronLeft className="h-4 w-4" />
                <div className="text-left">
                  <p className="text-xs text-text-muted">Previous</p>
                  <p className="font-medium">Ch. {prevChapter.number}: {prevChapter.title}</p>
                </div>
              </button>
            ) : (
              <div />
            )}
            {nextChapter ? (
              <button
                onClick={() => goToChapter(nextChapter)}
                className="flex items-center gap-2 text-sm text-text-muted hover:text-text transition-colors cursor-pointer rounded-lg px-3 py-2 -mx-3"
              >
                <div className="text-right">
                  <p className="text-xs text-text-muted">Next</p>
                  <p className="font-medium">Ch. {nextChapter.number}: {nextChapter.title}</p>
                </div>
                <ChevronRight className="h-4 w-4" />
              </button>
            ) : (
              <div />
            )}
          </nav>

          {/* Chapter 1 copyright (bottom of page) */}
          {currentChapter.number === 1 && (
            <aside className="mt-10 rounded-lg border border-border/60 bg-surface-raised/60 px-5 py-4 text-sm leading-relaxed text-text-muted">
              <p>&copy; 2026 Manav Sehgal.</p>
              <p>
                Licensed under{" "}
                <a
                  href="https://creativecommons.org/licenses/by-nc/4.0/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:text-primary/80 transition-colors"
                >
                  Creative Commons Attribution-NonCommercial 4.0 (CC BY-NC 4.0)
                </a>
                .
              </p>
            </aside>
          )}
        </article>
      </div>

      {/* Progress bar */}
      <div className="h-0.5 bg-surface-raised shrink-0">
        <div
          className="h-full bg-primary transition-all duration-300"
          style={{ width: `${(progress[currentChapter.id]?.progress ?? 0) * 100}%` }}
        />
      </div>
    </div>
  );
}
