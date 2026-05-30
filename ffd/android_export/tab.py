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

        # Sub-tab 3: Mass convert character sheets -------------------------
        mc_frame = ttk.Frame(notebook)
        notebook.add(mc_frame, text="Mass convert characters")
        self._build_mass_convert_tab(mc_frame)

        # Sub-tab 4: Mass convert tileset sheets ---------------------------
        mt_frame = ttk.Frame(notebook)
        notebook.add(mt_frame, text="Mass convert tilesets")
        self._build_mass_convert_tilesets_tab(mt_frame)

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

    # ------------------------------------------------------------------ #
    # Sub-tab 3: Mass convert characters
    # ------------------------------------------------------------------ #
    def _build_mass_convert_tab(self, parent):
        intro = ttk.Label(parent, text=(
            "Run the Mobile -> Android sprite converter over every Mobile "
            "chpk entry / palette across the loaded .sp slots. Each entry "
            "is matched against the appropriate template "
            "(character_main.json by default, character_frog.json for "
            "chpk[2], character_mini.json for chpk[4], or "
            "character_battle.json for 112x48 sheets) and written as "
            "fldchr<id>_<palette>.png in the chosen folder. Existing "
            "files in that folder are overwritten."),
            wraplength=820)
        intro.pack(anchor="w", padx=4, pady=4)

        outf = ttk.Frame(parent)
        outf.pack(fill="x", padx=4, pady=4)
        ttk.Label(outf, text="Output folder:").pack(side="left")
        self._mc_out_var = tk.StringVar(
            value=str(Path.home() / "ffd_converted_characters"))
        ttk.Entry(outf, textvariable=self._mc_out_var).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(outf, text="Choose...",
                   command=lambda: self._pick_dir(self._mc_out_var)
                   ).pack(side="left")

        # Filter options
        optf = ttk.LabelFrame(parent, text="Filter")
        optf.pack(fill="x", padx=4, pady=4)
        self._mc_only_first_pal = tk.BooleanVar(value=False)
        ttk.Checkbutton(optf, text=
            "Only emit palette 0 (skip _1.._N variants)",
            variable=self._mc_only_first_pal
            ).grid(row=0, column=0, sticky="w", padx=6, pady=2)
        self._mc_skip_existing = tk.BooleanVar(value=False)
        ttk.Checkbutton(optf, text=
            "Skip if output file already exists",
            variable=self._mc_skip_existing
            ).grid(row=0, column=1, sticky="w", padx=6, pady=2)

        runf = ttk.Frame(parent); runf.pack(fill="x", padx=4, pady=4)
        self._mc_run_btn = ttk.Button(runf, text="Mass convert",
                                       command=self._run_mass_convert)
        self._mc_run_btn.pack(side="left")
        self._mc_prog = ttk.Progressbar(runf, mode="indeterminate")
        self._mc_prog.pack(side="left", fill="x", expand=True, padx=8)

        logf = ttk.LabelFrame(parent, text="Log")
        logf.pack(fill="both", expand=True, padx=4, pady=4)
        self._mc_log = ScrolledText(logf, height=20, wrap="word",
                                    font=("TkFixedFont", 9))
        self._mc_log.pack(fill="both", expand=True, padx=4, pady=4)

    def _mc_logln(self, msg):
        self._mc_log.insert("end", msg + "\n")
        self._mc_log.see("end")
        self._mc_log.update_idletasks()

    def _run_mass_convert(self):
        """Kick off mass conversion in a worker thread."""
        out_path = self._mc_out_var.get().strip()
        if not out_path:
            messagebox.showinfo("Output folder",
                "Choose an output folder first.")
            return
        try:
            Path(out_path).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot create output folder:\n{e}")
            return
        self._mc_log.delete("1.0", "end")
        self._mc_run_btn.config(state="disabled")
        self._mc_prog.start(10)
        t = threading.Thread(target=self._mass_convert_worker,
                             args=(out_path,), daemon=True)
        t.start()

    def _mass_convert_worker(self, out_path):
        """Iterate every Mobile chpk entry across loaded .sp slots,
        pick the appropriate template + convert + save."""
        try:
            self._mass_convert_impl(out_path)
        except Exception as e:
            self._mc_logln(f"FATAL: {e}")
            self._mc_logln(traceback.format_exc())
        finally:
            self.after(0, self._mass_convert_done)

    def _mass_convert_done(self):
        self._mc_prog.stop()
        self._mc_run_btn.config(state="normal")

    def _mass_convert_impl(self, out_path):
        # Imports kept local so the tab module loads cleanly without
        # PIL/Tk during headless test
        import os
        from ..sprites.container import parse_sprite_container
        from ..images.ic import render_ic
        from ..sprites.mobile_to_android import (
            load_mapping_spec, convert_mobile_sheet_to_android,
        )
        from ..animation.parser import parse_field_anm, parse_btl_anm

        # Cache the parsed anim files (loaded once per run)
        obb = self.data.obb_files or {}
        field_entries = None
        btl_entries = None
        if "field_anm.dat" in obb:
            try: field_entries = parse_field_anm(obb["field_anm.dat"])
            except Exception as e: self._mc_logln(f"WARN field_anm: {e}")
        if "btlanm_sp.dat" in obb:
            try: btl_entries = parse_btl_anm(obb["btlanm_sp.dat"])
            except Exception as e: self._mc_logln(f"WARN btlanm_sp: {e}")

        # Locate templates folder
        here = os.path.dirname(os.path.abspath(__file__))
        templates_dir = os.path.normpath(
            os.path.join(here, "..", "sprites", "mappings"))
        self._mc_logln(f"Templates: {templates_dir}")
        self._mc_logln(f"Output:    {out_path}")
        self._mc_logln(f"Has field_anm: {field_entries is not None}, "
                       f"has btlanm: {btl_entries is not None}")
        self._mc_logln("")

        # Size-based default rule (mirrors SpriteConverterTab)
        MAIN_SIZES = ((80,144),(80,72),(64,72),(48,72))
        BATTLE_SIZE = (112,48)
        ENTRY_OVR = {2: "character_frog.json", 4: "character_mini.json"}

        def default_template(size, entry):
            if size == BATTLE_SIZE: return "character_battle.json"
            if size in MAIN_SIZES:
                return ENTRY_OVR.get(entry, "character_main.json")
            return None

        # Cache loaded templates so we don't re-read JSON for each entry
        tpl_cache = {}
        def load_template(name):
            if name not in tpl_cache:
                p = os.path.join(templates_dir, name)
                if not os.path.exists(p):
                    tpl_cache[name] = None
                else:
                    try:
                        tpl_cache[name] = load_mapping_spec(p)
                    except Exception as e:
                        self._mc_logln(f"WARN template {name}: {e}")
                        tpl_cache[name] = None
            return tpl_cache[name]

        n_done = 0
        n_skipped = 0
        n_failed = 0
        for slot_label, files in (self.data.sp_slots or {}).items():
            if not files:
                continue
            chpk = files.get("chpk.dat") if hasattr(files, "get") else None
            if chpk is None:
                continue
            self._mc_logln(f"[{slot_label}] scanning chpk.dat...")
            try:
                entries = list(parse_sprite_container(chpk))
            except Exception as e:
                self._mc_logln(f"  parse failed: {e}")
                continue
            for (e_idx, v_idx, ic, _raw) in entries:
                if self._mc_only_first_pal.get() and v_idx != 0:
                    continue
                size = (ic.width, ic.height)
                tpl_name = default_template(size, e_idx)
                if tpl_name is None:
                    n_skipped += 1
                    continue
                tpl = load_template(tpl_name)
                if tpl is None:
                    self._mc_logln(
                        f"  chpk[{e_idx:02d}] pal{v_idx:02d} {size}: "
                        f"NO TEMPLATE ({tpl_name})")
                    n_skipped += 1
                    continue

                out_file = os.path.join(
                    out_path, f"fldchr{e_idx}_{v_idx}.png")
                if (self._mc_skip_existing.get()
                        and os.path.exists(out_file)):
                    n_skipped += 1
                    continue

                # Customize template for this specific (entry, palette)
                import copy
                spec = copy.deepcopy(tpl)
                ms = spec.setdefault("mobile_source", {})
                ms["chpk_entry"] = e_idx
                ms["palette"] = v_idx
                at = spec.setdefault("android_target", {})
                at["fldchr_id"] = e_idx

                # Pick the right anim entry from the right parser
                mode = at.get("mode", "field")
                anim_entry = None
                if mode == "battle":
                    be = at.get("btl_entry", 0)
                    bs = at.get("btl_sub", 0)
                    if btl_entries:
                        for be_obj in btl_entries:
                            if (be_obj.get("btl_entry") == be
                                    and be_obj.get("btl_sub") == bs):
                                anim_entry = be_obj
                                break
                else:
                    fae = at.get("field_anm_entry", 1)
                    if field_entries and 0 <= fae < len(field_entries):
                        anim_entry = field_entries[fae]

                if anim_entry is None:
                    self._mc_logln(
                        f"  chpk[{e_idx:02d}] pal{v_idx:02d}: "
                        f"no anim entry for {mode} (skipped)")
                    n_skipped += 1
                    continue

                try:
                    mobile_img = render_ic(ic).convert("RGBA")
                    out_img = convert_mobile_sheet_to_android(
                        mobile_img, anim_entry, spec, fill_missing=False)
                    out_img.save(out_file)
                    n_done += 1
                    self._mc_logln(
                        f"  chpk[{e_idx:02d}] pal{v_idx:02d} {size} "
                        f"-> {os.path.basename(out_file)} ({tpl_name})")
                except Exception as e:
                    n_failed += 1
                    self._mc_logln(
                        f"  chpk[{e_idx:02d}] pal{v_idx:02d}: FAIL: {e}")

        self._mc_logln("")
        self._mc_logln(f"DONE: {n_done} converted, "
                       f"{n_skipped} skipped, {n_failed} failed.")

    # ------------------------------------------------------------------ #
    # Sub-tab 4: Mass convert tilesets
    # ------------------------------------------------------------------ #
    def _build_mass_convert_tilesets_tab(self, parent):
        intro = ttk.Label(parent, text=(
            "Run the Mobile -> Android tileset converter over every "
            "Mobile cpk entry across the loaded .sp slots. Each entry "
            "is auto-matched to its Android mc_id via cpk_to_mc.json "
            "(with numeric fallback when missing) and written as "
            "mc<id>_0.png (variant 0). Non-zero color variants of each "
            "tileset are handled per the 'Variant strategy' option "
            "(verbatim copy from Android, or palette swap from the "
            "Mobile-sourced base). Existing files in the output folder "
            "are overwritten."),
            wraplength=820)
        intro.pack(anchor="w", padx=4, pady=4)

        outf = ttk.Frame(parent)
        outf.pack(fill="x", padx=4, pady=4)
        ttk.Label(outf, text="Output folder:").pack(side="left")
        self._mt_out_var = tk.StringVar(
            value=str(Path.home() / "ffd_converted_tilesets"))
        ttk.Entry(outf, textvariable=self._mt_out_var).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(outf, text="Choose...",
                   command=lambda: self._pick_dir(self._mt_out_var)
                   ).pack(side="left")

        # Filter / strategy options
        optf = ttk.LabelFrame(parent, text="Options")
        optf.pack(fill="x", padx=4, pady=4)
        self._mt_fill_from_android = tk.BooleanVar(value=True)
        ttk.Checkbutton(optf,
            text="Fill missing tiles from Android original",
            variable=self._mt_fill_from_android
            ).grid(row=0, column=0, sticky="w", padx=6, pady=2)
        self._mt_skip_existing = tk.BooleanVar(value=False)
        ttk.Checkbutton(optf,
            text="Skip if output file already exists",
            variable=self._mt_skip_existing
            ).grid(row=0, column=1, sticky="w", padx=6, pady=2)
        self._mt_include_variants = tk.BooleanVar(value=True)
        ttk.Checkbutton(optf,
            text="Also emit non-zero variants (mc_<id>_1, _2, ...)",
            variable=self._mt_include_variants
            ).grid(row=1, column=0, sticky="w", padx=6, pady=2)
        ttk.Label(optf, text="Variant strategy:"
                  ).grid(row=2, column=0, sticky="w", padx=6, pady=2)
        self._mt_palette_strategy = tk.StringVar(value="verbatim")
        ttk.Combobox(optf, textvariable=self._mt_palette_strategy,
                     values=("verbatim", "swap"), width=10,
                     state="readonly"
                     ).grid(row=2, column=1, sticky="w", padx=6, pady=2)
        ttk.Label(optf,
            text=("verbatim = copy Android variant byte-for-byte (lossless, "
                  "doesn't reflect Mobile edits); swap = re-color Mobile "
                  "base via palette LUT extracted from Android variants"),
            wraplength=820, foreground="#666"
            ).grid(row=3, column=0, columnspan=2,
                   sticky="w", padx=6, pady=2)

        runf = ttk.Frame(parent); runf.pack(fill="x", padx=4, pady=4)
        self._mt_run_btn = ttk.Button(runf, text="Mass convert tilesets",
                                       command=self._run_mass_convert_tilesets)
        self._mt_run_btn.pack(side="left")
        self._mt_prog = ttk.Progressbar(runf, mode="indeterminate")
        self._mt_prog.pack(side="left", fill="x", expand=True, padx=8)

        logf = ttk.LabelFrame(parent, text="Log")
        logf.pack(fill="both", expand=True, padx=4, pady=4)
        self._mt_log = ScrolledText(logf, height=20, wrap="word",
                                    font=("TkFixedFont", 9))
        self._mt_log.pack(fill="both", expand=True, padx=4, pady=4)

    def _mt_logln(self, msg):
        self._mt_log.insert("end", msg + "\n")
        self._mt_log.see("end")
        self._mt_log.update_idletasks()

    def _run_mass_convert_tilesets(self):
        out_path = self._mt_out_var.get().strip()
        if not out_path:
            messagebox.showinfo("Output folder",
                "Choose an output folder first.")
            return
        try:
            Path(out_path).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot create output folder:\n{e}")
            return
        self._mt_log.delete("1.0", "end")
        self._mt_run_btn.config(state="disabled")
        self._mt_prog.start(10)
        import threading
        t = threading.Thread(target=self._mt_worker,
                             args=(out_path,), daemon=True)
        t.start()

    def _mt_worker(self, out_path):
        try:
            self._mt_impl(out_path)
        except Exception as e:
            self._mt_logln(f"FATAL: {e}")
            self._mt_logln(traceback.format_exc())
        finally:
            self.after(0, self._mt_done)

    def _mt_done(self):
        self._mt_prog.stop()
        self._mt_run_btn.config(state="normal")

    def _mt_impl(self, out_path):
        """Iterate every Mobile cpk entry across loaded .sp slots, run
        the tileset converter, write mc{id}_0.png. Optionally also
        write non-zero variants via verbatim copy or palette swap.
        """
        import os
        from ..tilesets.parser import MobileTilesetResolver
        from ..sprites.mobile_tile_to_android import (
            convert_mobile_tileset_to_android,
            apply_variant_palette_swap,
            lookup_mc_for_cpk,
            load_android_mc_png,
            list_android_mc_variants,
            make_tileset_starter_spec,
        )

        obb = self.data.obb_files or {}
        cpk_to_mc = self.data.cpk_to_mc() or {}

        # Cache loaded cpk_to_mc for telemetry
        self._mt_logln(f"Output:         {out_path}")
        self._mt_logln(f"Fill missing:   {bool(self._mt_fill_from_android.get())}")
        self._mt_logln(f"Include var>0:  {bool(self._mt_include_variants.get())}")
        self._mt_logln(f"Strategy:       {self._mt_palette_strategy.get()}")
        self._mt_logln(f"cpk_to_mc.json: "
                       f"{len(cpk_to_mc)} chapter entries loaded" if cpk_to_mc
                       else "cpk_to_mc.json: MISSING (numeric fallback only)")
        self._mt_logln("")

        n_done = 0
        n_skipped = 0
        n_failed = 0
        n_variants = 0

        # Track which mc_ids we've already emitted to avoid re-writing variants
        # multiple times when several cpk entries map to the same mc_id.
        emitted = set()  # (mc_id, variant)

        for slot_label, files in (self.data.sp_slots or {}).items():
            if not files:
                continue
            try:
                resolver = MobileTilesetResolver(files)
            except Exception as e:
                self._mt_logln(f"[{slot_label}] resolver failed: {e}")
                continue
            cpks = sorted(resolver.cpk_index.keys())
            if not cpks:
                continue
            self._mt_logln(f"[{slot_label}] {len(cpks)} cpk entries")

            for cpk_entry in cpks:
                try:
                    mobile_img = resolver.get(cpk_entry, 0)
                except Exception as e:
                    self._mt_logln(f"  cpk[{cpk_entry:02d}]: render failed: {e}")
                    n_failed += 1
                    continue
                if mobile_img is None:
                    n_skipped += 1
                    continue

                # Look up Android mc_id
                mc_id, variant, source = lookup_mc_for_cpk(
                    cpk_to_mc, slot_label, cpk_entry)
                if mc_id is None:
                    self._mt_logln(
                        f"  cpk[{cpk_entry:02d}]: no mc_id "
                        f"(source: {source})")
                    n_skipped += 1
                    continue

                # Load Android original for fill_missing + size
                android_orig = load_android_mc_png(obb, mc_id, 0)
                # Build a base spec
                spec = make_tileset_starter_spec(
                    f"cpk{cpk_entry}", cpk_entry=cpk_entry,
                    mc_id=mc_id, variant=0,
                    chapter=slot_label,
                    fill_from_android=bool(self._mt_fill_from_android.get()),
                    palette_strategy=self._mt_palette_strategy.get(),
                )

                # Emit variant 0 (always Mobile-sourced)
                key0 = (mc_id, 0)
                out_file = os.path.join(out_path, f"mc{mc_id}_0.png")
                if (self._mt_skip_existing.get()
                        and os.path.exists(out_file)) or key0 in emitted:
                    pass
                else:
                    try:
                        out_img = convert_mobile_tileset_to_android(
                            mobile_img, spec, android_orig)
                        out_img.save(out_file)
                        emitted.add(key0)
                        n_done += 1
                        self._mt_logln(
                            f"  cpk[{cpk_entry:02d}] -> "
                            f"mc{mc_id}_0.png  [{source}]")
                    except Exception as e:
                        self._mt_logln(
                            f"  cpk[{cpk_entry:02d}] -> mc{mc_id}_0: "
                            f"FAIL: {e}")
                        n_failed += 1

                # Emit non-zero variants if requested
                if self._mt_include_variants.get():
                    variants = list_android_mc_variants(obb, mc_id)
                    strategy = self._mt_palette_strategy.get()
                    for var in variants:
                        if var == 0:
                            continue
                        keyN = (mc_id, var)
                        if keyN in emitted:
                            continue
                        out_var = os.path.join(out_path,
                                                f"mc{mc_id}_{var}.png")
                        if (self._mt_skip_existing.get()
                                and os.path.exists(out_var)):
                            emitted.add(keyN)
                            continue

                        try:
                            if strategy == "verbatim":
                                # Copy the Android variant straight through
                                src_blob = obb.get(f"mc{mc_id}_{var}.png")
                                if not src_blob:
                                    continue
                                with open(out_var, "wb") as f:
                                    f.write(src_blob)
                            else:  # swap
                                base_pal = load_android_mc_png(
                                    obb, mc_id, 0, preserve_palette=True)
                                tgt_pal = load_android_mc_png(
                                    obb, mc_id, var, preserve_palette=True)
                                if base_pal is None or tgt_pal is None:
                                    self._mt_logln(
                                        f"    mc{mc_id}_{var}: paletted "
                                        f"variant missing, falling back to "
                                        f"verbatim")
                                    src_blob = obb.get(f"mc{mc_id}_{var}.png")
                                    if src_blob:
                                        with open(out_var, "wb") as f:
                                            f.write(src_blob)
                                else:
                                    # Re-run convert for variant 0 base, then swap
                                    base_spec = make_tileset_starter_spec(
                                        f"cpk{cpk_entry}",
                                        cpk_entry=cpk_entry, mc_id=mc_id,
                                        variant=0, chapter=slot_label,
                                        fill_from_android=bool(
                                            self._mt_fill_from_android.get()),
                                    )
                                    base_out = convert_mobile_tileset_to_android(
                                        mobile_img, base_spec, android_orig)
                                    swapped = apply_variant_palette_swap(
                                        base_out, base_pal, tgt_pal)
                                    swapped.save(out_var)
                            emitted.add(keyN)
                            n_variants += 1
                        except Exception as e:
                            self._mt_logln(
                                f"    mc{mc_id}_{var}: FAIL: {e}")
                            n_failed += 1

        self._mt_logln("")
        self._mt_logln(f"DONE: {n_done} mc_0 converted, "
                       f"{n_variants} variants, "
                       f"{n_skipped} skipped, {n_failed} failed.")
