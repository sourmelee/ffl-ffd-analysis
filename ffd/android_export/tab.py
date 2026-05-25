"""GUI tab for the Mobile -> Android exporter + PNG -> .dat encoder."""

from __future__ import annotations

import threading
import traceback
from pathlib import Path

from ..gui_stub import tk, ttk, filedialog, messagebox, ScrolledText
from ..gui_core.base import TabBase

from .exporter import (
    AndroidExportOptions, export_all_chapters,
)
from .icp import encode_icp_directory


class AndroidExportTab(TabBase):
    """Tab: convert loaded .sp data into Android-formatted PNGs, OR re-encode
    a folder of PNGs back into ICP .dat files."""

    LABEL = "Android Export"

    def __init__(self, parent, data):
        super().__init__(parent, data)
        self._build()

    # ----------------------------- layout -------------------------------- #
    def _build(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        # Sub-tab 1: Mobile -> Android extractor ---------------------------
        exp_frame = ttk.Frame(notebook)
        notebook.add(exp_frame, text="Extract Mobile -> Android PNGs")
        self._build_extract_tab(exp_frame)

        # Sub-tab 2: PNG folder -> .dat encoder ----------------------------
        enc_frame = ttk.Frame(notebook)
        notebook.add(enc_frame, text="Encode PNG -> .dat")
        self._build_encode_tab(enc_frame)

    def _build_extract_tab(self, parent):
        intro = ttk.Label(parent, text=(
            "Extract assets from every loaded .sp scratchpad in the "
            "Android filename format (mon<id>_<var>.png, "
            "fldchr<id>_<var>.png, mc<id>_<pal>.png). 2x nearest-neighbor "
            "upscaling, one subfolder per chapter."),
            wraplength=820)
        intro.pack(anchor="w", padx=4, pady=4)

        # Output folder
        outf = ttk.Frame(parent)
        outf.pack(fill="x", padx=4, pady=4)
        ttk.Label(outf, text="Output folder:").pack(side="left")
        self._out_var = tk.StringVar(
            value=str(Path.home() / "ffd_android_export"))
        ttk.Entry(outf, textvariable=self._out_var).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(outf, text="Choose...",
                   command=self._pick_out).pack(side="left")

        # Options
        optf = ttk.LabelFrame(parent, text="Options")
        optf.pack(fill="x", padx=4, pady=4)
        self._var_monsters = tk.BooleanVar(value=True)
        self._var_chars    = tk.BooleanVar(value=True)
        self._var_tiles    = tk.BooleanVar(value=True)
        self._var_gifs     = tk.BooleanVar(value=True)
        ttk.Checkbutton(optf, text="Monsters (ene.dat) -> mon<id>_<var>.png",
                        variable=self._var_monsters).grid(row=0, column=0, sticky="w", padx=6, pady=2)
        ttk.Checkbutton(optf, text="Characters (chpk.dat) -> fldchr<id>_<var>.png",
                        variable=self._var_chars).grid(row=0, column=1, sticky="w", padx=6, pady=2)
        ttk.Checkbutton(optf, text="Tilesets (cpk*.dat) -> mc<id>_<pal>.png",
                        variable=self._var_tiles).grid(row=1, column=0, sticky="w", padx=6, pady=2)
        ttk.Checkbutton(optf, text="Include hidden-GIF entries (some monsters)",
                        variable=self._var_gifs).grid(row=1, column=1, sticky="w", padx=6, pady=2)

        # Scale
        scalef = ttk.Frame(optf)
        scalef.grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=2)
        ttk.Label(scalef, text="Scale (nearest-neighbor):").pack(side="left")
        self._scale_var = tk.IntVar(value=2)
        ttk.Spinbox(scalef, from_=1, to=4, textvariable=self._scale_var,
                    width=4).pack(side="left", padx=4)

        # Run button + log
        runf = ttk.Frame(parent)
        runf.pack(fill="x", padx=4, pady=4)
        self._run_btn = ttk.Button(runf, text="Export",
                                   command=self._run_extract)
        self._run_btn.pack(side="left")
        self._prog = ttk.Progressbar(runf, mode="indeterminate")
        self._prog.pack(side="left", fill="x", expand=True, padx=8)

        log_frame = ttk.LabelFrame(parent, text="Log")
        log_frame.pack(fill="both", expand=True, padx=4, pady=4)
        self._log = ScrolledText(log_frame, height=15, wrap="word",
                                 font=("TkFixedFont", 9))
        self._log.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_encode_tab(self, parent):
        intro = ttk.Label(parent, text=(
            "Encode a folder of PNGs back into ICP-wrapped .dat files "
            "(Android-readable). The encoder is the inverse of the "
            "proper-mode .obb extractor: pick a PNG folder, the output "
            ".dat folder, and optionally an originals folder (raw_obb/) "
            "so header metadata is preserved per-file."),
            wraplength=820)
        intro.pack(anchor="w", padx=4, pady=4)

        # PNG source folder
        pf = ttk.Frame(parent)
        pf.pack(fill="x", padx=4, pady=4)
        ttk.Label(pf, text="PNG folder:").pack(side="left")
        self._enc_png_var = tk.StringVar()
        ttk.Entry(pf, textvariable=self._enc_png_var).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(pf, text="Choose...",
                   command=lambda: self._pick_dir(self._enc_png_var)
                   ).pack(side="left")

        # Output .dat folder
        df = ttk.Frame(parent)
        df.pack(fill="x", padx=4, pady=4)
        ttk.Label(df, text=".dat output folder:").pack(side="left")
        self._enc_out_var = tk.StringVar()
        ttk.Entry(df, textvariable=self._enc_out_var).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(df, text="Choose...",
                   command=lambda: self._pick_dir(self._enc_out_var)
                   ).pack(side="left")

        # Reference raw_obb folder (optional)
        rf = ttk.Frame(parent)
        rf.pack(fill="x", padx=4, pady=4)
        ttk.Label(rf, text="Reference raw_obb folder (optional):").pack(side="left")
        self._enc_ref_var = tk.StringVar()
        ttk.Entry(rf, textvariable=self._enc_ref_var).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(rf, text="Choose...",
                   command=lambda: self._pick_dir(self._enc_ref_var)
                   ).pack(side="left")
        ttk.Label(parent, text=(
            "When given, matching <name>.dat files in this folder are read "
            "to copy filter flag and unknown header bytes -- byte-faithful "
            "round-trip for existing assets."),
            wraplength=820, foreground="#666").pack(anchor="w", padx=4)

        # Filter flag default
        ff = ttk.Frame(parent)
        ff.pack(fill="x", padx=4, pady=4)
        ttk.Label(ff, text="Default filter flag (when no reference):").pack(side="left")
        self._enc_flag_var = tk.IntVar(value=1)
        ttk.Radiobutton(ff, text="1 = GL_NEAREST (pixel art)",
                        variable=self._enc_flag_var, value=1).pack(side="left", padx=4)
        ttk.Radiobutton(ff, text="0 = GL_LINEAR (smooth)",
                        variable=self._enc_flag_var, value=0).pack(side="left", padx=4)

        # Run + log
        runf = ttk.Frame(parent)
        runf.pack(fill="x", padx=4, pady=4)
        self._enc_btn = ttk.Button(runf, text="Encode",
                                   command=self._run_encode)
        self._enc_btn.pack(side="left")
        self._enc_prog = ttk.Progressbar(runf, mode="indeterminate")
        self._enc_prog.pack(side="left", fill="x", expand=True, padx=8)

        log_frame = ttk.LabelFrame(parent, text="Log")
        log_frame.pack(fill="both", expand=True, padx=4, pady=4)
        self._enc_log = ScrolledText(log_frame, height=12, wrap="word",
                                     font=("TkFixedFont", 9))
        self._enc_log.pack(fill="both", expand=True, padx=4, pady=4)

    # ----------------------------- helpers ------------------------------- #
    def _pick_out(self):
        d = filedialog.askdirectory(initialdir=self._out_var.get() or ".")
        if d:
            self._out_var.set(d)

    def _pick_dir(self, var):
        d = filedialog.askdirectory(initialdir=var.get() or ".")
        if d:
            var.set(d)

    def _log_line(self, log_widget, line):
        log_widget.insert("end", line + "\n")
        log_widget.see("end")
        log_widget.update_idletasks()

    # ----------------------------- extract ------------------------------- #
    def _run_extract(self):
        outdir = Path(self._out_var.get())
        if not self.data.sp_slots or not any(self.data.sp_slots.values()):
            messagebox.showinfo(
                "No .sp loaded",
                "Load at least one .sp scratchpad via the Files tab "
                "before exporting.")
            return
        opts = AndroidExportOptions(
            scale=max(1, int(self._scale_var.get())),
            include_monsters=self._var_monsters.get(),
            include_characters=self._var_chars.get(),
            include_tilesets=self._var_tiles.get(),
            include_hidden_gifs=self._var_gifs.get(),
        )
        self._log.delete("1.0", "end")
        self._run_btn.configure(state="disabled")
        self._prog.start(40)

        def worker():
            try:
                export_all_chapters(
                    self.data.sp_slots, outdir, opts,
                    log=lambda m: self._log_line(self._log, m),
                )
            except Exception:
                self._log_line(self._log, "ERROR:\n" + traceback.format_exc())
            finally:
                self._prog.stop()
                self._run_btn.configure(state="normal")

        threading.Thread(target=worker, daemon=True).start()

    # ----------------------------- encode -------------------------------- #
    def _run_encode(self):
        png_dir = self._enc_png_var.get().strip()
        out_dir = self._enc_out_var.get().strip()
        ref_dir = self._enc_ref_var.get().strip() or None
        if not png_dir or not Path(png_dir).is_dir():
            messagebox.showerror("Pick a PNG folder",
                                 "Choose a folder containing PNGs to encode.")
            return
        if not out_dir:
            messagebox.showerror("Pick an output folder",
                                 "Choose a folder for the produced .dat files.")
            return
        self._enc_log.delete("1.0", "end")
        self._enc_btn.configure(state="disabled")
        self._enc_prog.start(40)
        flag = int(self._enc_flag_var.get())

        def worker():
            try:
                n = encode_icp_directory(
                    png_dir, out_dir, ref_raw_dir=ref_dir,
                    filter_flag=flag,
                    log=lambda m: self._log_line(self._enc_log, m),
                )
                self._log_line(self._enc_log, f"Done: {n} .dat files written.")
            except Exception:
                self._log_line(self._enc_log,
                               "ERROR:\n" + traceback.format_exc())
            finally:
                self._enc_prog.stop()
                self._enc_btn.configure(state="normal")

        threading.Thread(target=worker, daemon=True).start()
