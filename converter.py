"""
Drop-to-JPG Converter v4
Rounded buttons, frosted glass, smart convert button states.
"""

import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import fitz
except ImportError:
    fitz = None


# ── Supported formats ──────────────────────────────────────────────────────────
SUPPORTED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".tiff", ".tif",
                 ".bmp", ".webp", ".ico"}

# ── Palette ────────────────────────────────────────────────────────────────────
BG        = "#F5F0E8"
SURFACE   = "#EDE8DC"
SURFACE2  = "#DDD6C8"
OLIVE     = "#6B7C45"
OLIVE_DK  = "#4E5C30"
OLIVE_LT  = "#8A9E60"
BROWN     = "#7A5C3E"
BROWN_LT  = "#A07850"
HONEY     = "#D4900A"
HONEY_DK  = "#B07800"
HONEY_LT  = "#E8B040"
UMBER     = "#A63228"
TEXT      = "#2E2A22"
SUBTEXT   = "#8C7A68"

# Frosted glass colours (semi-transparent feel via blended tones)
FROST_BG   = "#EAE4D8"   # slightly lighter than SURFACE
FROST_BD   = "#C8C0B0"   # soft border

# Convert button states
BTN_GREY   = {"bg": "#C4BDB4", "fg": "#8C7A68", "active_bg": "#C4BDB4"}  # nothing to do
BTN_BLACK  = {"bg": "#2E2A22", "fg": "#F5F0E8", "active_bg": "#1A1714"}  # ready
BTN_GREEN  = {"bg": OLIVE,     "fg": "#FFFFFF",  "active_bg": OLIVE_DK}  # done

STATUS_COLORS = {
    "ready":      SUBTEXT,
    "converting": HONEY,
    "done":       OLIVE,
    "error":      UMBER,
}

FONT = "Helvetica Neue"


# ── Rounded canvas button ──────────────────────────────────────────────────────

class RoundedButton(tk.Canvas):
    """A button drawn on a Canvas so we get true rounded corners, no white box."""

    def __init__(self, parent, text, command=None,
                 bg="#2E2A22", fg="#FFFFFF", active_bg=None,
                 font=None, radius=8, padx=14, pady=6,
                 width=None, height=None, **kwargs):
        self._bg       = bg
        self._fg       = fg
        self._active   = active_bg or bg
        self._text     = text
        self._command  = command
        self._radius   = radius
        self._padx     = padx
        self._pady     = pady
        self._font     = font or (FONT, 10)
        self._disabled = False

        # measure text to auto-size if not given
        tmp = tk.Label(parent, text=text, font=self._font)
        tw = tmp.winfo_reqwidth()
        th = tmp.winfo_reqheight()
        tmp.destroy()

        cw = width  or tw + padx * 2
        ch = height or th + pady * 2
        self._cw = cw
        self._ch = ch

        try:
            parent_bg = parent.cget("bg")
        except Exception:
            parent_bg = BG

        super().__init__(parent, width=cw, height=ch,
                         bg=parent_bg,
                         bd=0, highlightthickness=0,
                         cursor="hand2", **kwargs)

        # inset 1px on all sides so smooth=True polygon never clips the edge
        self._rect = self.create_rounded_rect(1, 1, cw - 1, ch - 1, radius, fill=bg)
        self._label = self.create_text(cw // 2, ch // 2,
                                       text=text, fill=fg,
                                       font=self._font, anchor="center")

        # re-sync bg after layout (parent bg sometimes resolves late)
        self.after(20, self._sync_bg)

        self.bind("<ButtonPress-1>",   self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>",           self._on_enter)
        self.bind("<Leave>",           self._on_leave)

    def _sync_bg(self):
        """Match canvas background to parent so no box shows around the button."""
        try:
            self.config(bg=self.master.cget("bg"))
        except Exception:
            pass

    def create_rounded_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [
            x1+r, y1,
            x2-r, y1,
            x2,   y1,
            x2,   y1+r,
            x2,   y2-r,
            x2,   y2,
            x2-r, y2,
            x1+r, y2,
            x1,   y2,
            x1,   y2-r,
            x1,   y1+r,
            x1,   y1,
        ]
        return self.create_polygon(pts, smooth=True, **kw)

    def _on_press(self, _):
        if not self._disabled:
            self.itemconfig(self._rect, fill=self._active)

    def _on_release(self, _):
        if not self._disabled:
            self.itemconfig(self._rect, fill=self._bg)
            if self._command:
                self._command()

    def _on_enter(self, _):
        if not self._disabled:
            self.itemconfig(self._rect, fill=self._active)

    def _on_leave(self, _):
        if not self._disabled:
            self.itemconfig(self._rect, fill=self._bg)

    def configure_btn(self, text=None, bg=None, fg=None, active_bg=None,
                      disabled=None):
        if text is not None:
            self._text = text
            self.itemconfig(self._label, text=text)
        if bg is not None:
            self._bg = bg
            self.itemconfig(self._rect, fill=bg)
        if fg is not None:
            self._fg = fg
            self.itemconfig(self._label, fill=fg)
        if active_bg is not None:
            self._active = active_bg
        if disabled is not None:
            self._disabled = disabled
            self.config(cursor="" if disabled else "hand2")


# ── Conversion logic ───────────────────────────────────────────────────────────

def pdf_to_jpgs(pdf_path: Path, out_dir: Path, dpi: int = 150) -> list:
    if fitz is None:
        raise RuntimeError("PyMuPDF not installed")
    doc = fitz.open(str(pdf_path))
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    out_paths = []
    stem = pdf_path.stem
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=mat, alpha=False)
        suffix = f"_p{i+1:03d}" if len(doc) > 1 else ""
        out_path = out_dir / f"{stem}{suffix}.jpg"
        counter = 1
        while out_path.exists():
            out_path = out_dir / f"{stem}{suffix}_{counter}.jpg"
            counter += 1
        pix.save(str(out_path))
        out_paths.append(out_path)
    doc.close()
    return out_paths


def image_to_jpg(img_path: Path, out_dir: Path) -> Path:
    if Image is None:
        raise RuntimeError("Pillow not installed")
    stem = img_path.stem
    out_path = out_dir / f"{stem}.jpg"
    counter = 1
    while out_path.exists() and out_path.resolve() != img_path.resolve():
        out_path = out_dir / f"{stem}_{counter}.jpg"
        counter += 1
    img = Image.open(str(img_path))
    if hasattr(img, "is_animated") and img.is_animated:
        img.seek(0)
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        if img.mode in ("RGBA", "LA"):
            bg.paste(img, mask=img.split()[-1])
        else:
            bg.paste(img)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    img.save(str(out_path), "JPEG", quality=92, optimize=True)
    return out_path


# ── File row ───────────────────────────────────────────────────────────────────

class FileRow:
    def __init__(self, parent_frame, file_path: Path, remove_cb):
        self.file_path = file_path
        self.remove_cb = remove_cb
        self.status = "ready"

        self.frame = tk.Frame(parent_frame, bg=SURFACE, pady=7, padx=10)
        self.frame.pack(fill="x", padx=0, pady=(0, 1))

        self._bar = tk.Frame(self.frame, bg=SURFACE2, width=4)
        self._bar.pack(side="left", fill="y", padx=(0, 10))

        ext = file_path.suffix.lower()
        badge_text = "PDF" if ext == ".pdf" else ext.lstrip(".").upper()[:4]
        badge = tk.Label(self.frame, text=badge_text, bg=HONEY, fg="white",
                         font=(FONT, 7, "bold"), width=4, pady=2)
        badge.pack(side="left", padx=(0, 10))

        name = file_path.name
        if len(name) > 46:
            name = name[:21] + "…" + name[-21:]
        self.name_label = tk.Label(self.frame, text=name, bg=SURFACE,
                                   fg=TEXT, font=(FONT, 10), anchor="w")
        self.name_label.pack(side="left", fill="x", expand=True)

        # remove button — small rounded canvas button, no white box
        self.rm_btn = RoundedButton(
            self.frame, text="✕", command=lambda: remove_cb(self),
            bg=SURFACE2, fg=SUBTEXT, active_bg=UMBER,
            font=(FONT, 9), radius=6, padx=6, pady=3)
        self.rm_btn.pack(side="right", padx=(6, 0))

        self.status_label = tk.Label(self.frame, text="Ready",
                                     bg=SURFACE, fg=SUBTEXT,
                                     font=(FONT, 9))
        self.status_label.pack(side="right", padx=(0, 8))

    def set_status(self, status: str, detail: str = ""):
        self.status = status
        labels = {
            "ready":      "Ready",
            "converting": "Converting…",
            "done":       "Done ✓",
            "error":      f"Error: {detail}",
        }
        bar_colors = {
            "ready":      SURFACE2,
            "converting": HONEY,
            "done":       OLIVE,
            "error":      UMBER,
        }
        self.status_label.config(
            text=labels.get(status, status),
            fg=STATUS_COLORS.get(status, TEXT))
        self._bar.config(bg=bar_colors.get(status, SURFACE2))

    def destroy(self):
        self.frame.destroy()


# ── App ────────────────────────────────────────────────────────────────────────

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Drop-to-JPG")
        self.root.geometry("580x610")
        self.root.minsize(480, 500)
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        self.out_dir = None
        self.rows = []
        self._conversion_done = False
        self._build_ui()

    def _build_ui(self):
        root = self.root

        # ── Header ────────────────────────────────────────────────────────────
        header = tk.Frame(root, bg=OLIVE, pady=14)
        header.pack(fill="x")
        tk.Label(header, text="Drop-to-JPG", bg=OLIVE, fg="white",
                 font=(FONT, 17, "bold")).pack(side="left", padx=18)
        tk.Label(header, text="Convert any image or PDF to JPG",
                 bg=OLIVE, fg="#C8D4A8",
                 font=(FONT, 10)).pack(side="left", pady=(5, 0))

        # ── Output folder bar (frosted) ───────────────────────────────────────
        dir_bar = tk.Frame(root, bg=FROST_BG, pady=9, padx=18,
                           highlightbackground=FROST_BD, highlightthickness=1)
        dir_bar.pack(fill="x")

        tk.Label(dir_bar, text="Output folder:", bg=FROST_BG, fg=BROWN,
                 font=(FONT, 9, "bold")).pack(side="left")

        self.dir_label = tk.Label(dir_bar,
                                  text="Same folder as each source file",
                                  bg=FROST_BG, fg=SUBTEXT,
                                  font=(FONT, 9), anchor="w")
        self.dir_label.pack(side="left", padx=10, fill="x", expand=True)

        RoundedButton(dir_bar, text="Change…",
                      command=self._choose_outdir,
                      bg=FROST_BD, fg=BROWN, active_bg=SURFACE2,
                      font=(FONT, 9), radius=7, padx=10, pady=4
                      ).pack(side="right")

        tk.Frame(root, bg=SURFACE2, height=1).pack(fill="x")

        # ── Drop zone ─────────────────────────────────────────────────────────
        drop_wrap = tk.Frame(root, bg=BG, padx=18, pady=14)
        drop_wrap.pack(fill="x")

        self.drop_zone = tk.Frame(drop_wrap, bg=FROST_BG,
                                  highlightbackground=HONEY,
                                  highlightthickness=2,
                                  cursor="hand2")
        self.drop_zone.pack(fill="x")

        # inner frame to allow centering via grid
        inner = tk.Frame(self.drop_zone, bg=FROST_BG)
        inner.pack(expand=True, fill="both", pady=22)

        tk.Label(inner, text="Drop files here",
                 bg=FROST_BG, fg=OLIVE,
                 font=(FONT, 15, "bold")).pack()
        tk.Label(inner,
                 text="PDF  ·  PNG  ·  JPG  ·  GIF  ·  TIFF  ·  BMP  ·  WEBP  ·  ICO",
                 bg=FROST_BG, fg=BROWN_LT,
                 font=(FONT, 9)).pack(pady=(3, 8))

        RoundedButton(inner, text="Browse files…",
                      command=self._browse_files,
                      bg=HONEY, fg="white", active_bg=HONEY_DK,
                      font=(FONT, 10, "bold"), radius=8, padx=16, pady=6
                      ).pack()

        if TkinterDnD is not None:
            def _reg(w):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)
            for w in [self.drop_zone, inner] + list(inner.winfo_children()):
                _reg(w)

        # ── File list header ──────────────────────────────────────────────────
        list_hdr = tk.Frame(root, bg=BG, pady=5, padx=18)
        list_hdr.pack(fill="x")

        self.count_label = tk.Label(list_hdr, text="No files added",
                                    bg=BG, fg=SUBTEXT, font=(FONT, 9))
        self.count_label.pack(side="left")

        RoundedButton(list_hdr, text="Clear all",
                      command=self._clear_all,
                      bg=SURFACE2, fg=SUBTEXT, active_bg=UMBER,
                      font=(FONT, 9), radius=6, padx=10, pady=3
                      ).pack(side="right")

        # ── Scrollable file list ──────────────────────────────────────────────
        list_outer = tk.Frame(root, bg=BG, padx=18)
        list_outer.pack(fill="both", expand=True)

        list_border = tk.Frame(list_outer, bg=SURFACE2, bd=0)
        list_border.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(list_border, bg=BG, bd=0,
                                highlightthickness=0, height=160)
        self.scrollbar = ttk.Scrollbar(list_border, orient="vertical",
                                       command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg=BG)
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self._on_yscroll)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.empty_label = tk.Label(self.canvas,
                                    text="Files you add will appear here",
                                    bg=BG, fg=SURFACE2,
                                    font=(FONT, 10, "italic"))
        self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

        # ── Bottom bar ────────────────────────────────────────────────────────
        tk.Frame(root, bg=SURFACE2, height=1).pack(fill="x")

        bottom = tk.Frame(root, bg=FROST_BG, pady=14, padx=18)
        bottom.pack(fill="x")

        prog_frame = tk.Frame(bottom, bg=FROST_BG)
        prog_frame.pack(side="left", fill="x", expand=True, padx=(0, 16))

        self.progress_label = tk.Label(prog_frame, text="",
                                       bg=FROST_BG, fg=SUBTEXT,
                                       font=(FONT, 8))
        self.progress_label.pack(anchor="w")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Honey.Horizontal.TProgressbar",
                        troughcolor=SURFACE2,
                        background=HONEY,
                        bordercolor=SURFACE2,
                        lightcolor=HONEY,
                        darkcolor=HONEY_DK,
                        thickness=5)
        self.progress = ttk.Progressbar(prog_frame, mode="determinate",
                                        style="Honey.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(3, 0))

        self.convert_btn = RoundedButton(
            bottom, text="Convert All  →",
            command=self._start_conversion,
            bg=BTN_GREY["bg"], fg=BTN_GREY["fg"],
            active_bg=BTN_GREY["active_bg"],
            font=(FONT, 11, "bold"), radius=10, padx=22, pady=9)
        self.convert_btn.pack(side="right")

    # ── Scrollbar visibility ───────────────────────────────────────────────────

    def _on_yscroll(self, first, last):
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.scrollbar.pack_forget()
        else:
            self.scrollbar.pack(side="right", fill="y")
        self.scrollbar.set(first, last)

    # ── Convert button state ───────────────────────────────────────────────────

    def _update_convert_btn(self):
        if self._conversion_done and all(r.status == "done" for r in self.rows) and self.rows:
            # all done — green
            self.convert_btn.configure_btn(
                text="All Done  ✓",
                bg=BTN_GREEN["bg"], fg=BTN_GREEN["fg"],
                active_bg=BTN_GREEN["active_bg"], disabled=False)
        elif self.rows and any(r.status not in ("done",) for r in self.rows):
            # files pending — black
            self.convert_btn.configure_btn(
                text="Convert All  →",
                bg=BTN_BLACK["bg"], fg=BTN_BLACK["fg"],
                active_bg=BTN_BLACK["active_bg"], disabled=False)
        else:
            # nothing to do — grey
            self.convert_btn.configure_btn(
                text="Convert All  →",
                bg=BTN_GREY["bg"], fg=BTN_GREY["fg"],
                active_bg=BTN_GREY["active_bg"], disabled=True)

    # ── Actions ────────────────────────────────────────────────────────────────

    def _choose_outdir(self):
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            self.out_dir = Path(d)
            short = str(self.out_dir)
            if len(short) > 55:
                short = "…" + short[-52:]
            self.dir_label.config(text=short, fg=BROWN)

    def _browse_files(self):
        files = filedialog.askopenfilenames(
            title="Select files to convert",
            filetypes=[
                ("Supported files",
                 "*.pdf *.png *.jpg *.jpeg *.gif *.tiff *.tif *.bmp *.webp *.ico"),
                ("All files", "*.*"),
            ]
        )
        for f in files:
            self._add_file(Path(f))

    def _on_drop(self, event):
        raw = event.data
        paths = []
        i = 0
        while i < len(raw):
            if raw[i] == "{":
                end = raw.index("}", i)
                paths.append(raw[i+1:end])
                i = end + 2
            else:
                j = raw.find(" ", i)
                if j == -1:
                    paths.append(raw[i:])
                    break
                paths.append(raw[i:j])
                i = j + 1
        for p in paths:
            self._add_file(Path(p))

    def _add_file(self, path: Path):
        if not path.is_file():
            return
        if path.suffix.lower() not in SUPPORTED_EXT:
            messagebox.showwarning(
                "Unsupported file",
                f'"{path.name}" cannot be converted.\n\n'
                f'Accepted: PDF, PNG, JPG, GIF, TIFF, BMP, WEBP, ICO')
            return
        if any(r.file_path == path for r in self.rows):
            return
        self.empty_label.place_forget()
        self._conversion_done = False
        row = FileRow(self.scroll_frame, path, self._remove_row)
        self.rows.append(row)
        self._update_count()
        self._update_convert_btn()

    def _remove_row(self, row: FileRow):
        row.destroy()
        self.rows.remove(row)
        self._update_count()
        self._update_convert_btn()
        if not self.rows:
            self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

    def _clear_all(self):
        for row in self.rows[:]:
            row.destroy()
        self.rows.clear()
        self._conversion_done = False
        self._update_count()
        self.progress["value"] = 0
        self.progress_label.config(text="", fg=SUBTEXT)
        self._update_convert_btn()
        self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

    def _update_count(self):
        n = len(self.rows)
        if n == 0:
            self.count_label.config(text="No files added", fg=SUBTEXT)
        else:
            self.count_label.config(
                text=f"{n} file{'s' if n != 1 else ''} queued", fg=BROWN)

    # ── Conversion ─────────────────────────────────────────────────────────────

    def _start_conversion(self):
        if not self.rows:
            return
        pending = [r for r in self.rows if r.status != "done"]
        if not pending:
            return
        self.convert_btn.configure_btn(
            text="Converting…",
            bg=SURFACE2, fg=SUBTEXT,
            active_bg=SURFACE2, disabled=True)
        threading.Thread(target=self._convert_all, args=(pending,),
                         daemon=True).start()

    def _convert_all(self, rows):
        total = len(rows)
        self.root.after(0, lambda: self.progress.configure(maximum=total, value=0))
        self.root.after(0, lambda: self.progress_label.config(
            text="Starting…", fg=SUBTEXT))

        for i, row in enumerate(rows):
            self.root.after(0, lambda r=row: r.set_status("converting"))
            self.root.after(0, lambda idx=i, t=total: self.progress_label.config(
                text=f"Converting {idx + 1} of {t}…", fg=HONEY_DK))
            try:
                out_dir = self.out_dir or row.file_path.parent
                out_dir.mkdir(parents=True, exist_ok=True)
                if row.file_path.suffix.lower() == ".pdf":
                    pdf_to_jpgs(row.file_path, out_dir)
                else:
                    image_to_jpg(row.file_path, out_dir)
                self.root.after(0, lambda r=row: r.set_status("done"))
            except Exception as exc:
                import traceback
                traceback.print_exc()
                msg = str(exc)[:60]
                self.root.after(0, lambda r=row, m=msg: r.set_status("error", m))

            self.root.after(0, lambda v=i+1: self.progress.configure(value=v))

        done  = sum(1 for r in rows if r.status == "done")
        errors = total - done

        def finish():
            self._conversion_done = True
            self._update_convert_btn()
            if errors == 0:
                self.progress_label.config(
                    text=f"All {total} file{'s' if total != 1 else ''} converted ✓",
                    fg=OLIVE)
            else:
                self.progress_label.config(
                    text=f"{done} converted, {errors} failed — see errors above",
                    fg=UMBER)

        self.root.after(0, finish)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    try:
        if TkinterDnD is not None:
            root = TkinterDnD.Tk()
        else:
            raise ImportError
    except Exception:
        import tkinter as tk
        root = tk.Tk()
        print("Warning: drag-and-drop unavailable, using browse mode only.")
    App(root)
    root.mainloop()
