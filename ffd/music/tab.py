"""Music / audio tab -- extract melodies from the Mobile and Android
``snd.dat`` containers (raw MFi ``.mld``) plus any streamed audio that
lives loose inside the Android ``.obb``.

The Mobile engine stores every sound as an MFi ("Melody Format for
i-mode") melody inside ``snd.dat``; see :mod:`ffd.music.parser`. Raw
``.mld`` export is byte-exact. Conversion to ``.mid`` is deferred because
these are MFi v5 blobs whose event stream is not yet decoded -- the
"Export .mid" control is present but disabled until that lands.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..gui_stub import (
    tk, ttk, filedialog, messagebox, ScrolledText,
)
from ..music.parser import parse_snd
from ..gui_core.helpers import open_in_default_app
from ..gui_core.base import TabBase


# Loose streamed audio the Android port may ship alongside snd.dat.
_ANDROID_AUDIO_EXTS = (".ogg", ".mp3", ".wav", ".m4a", ".mid", ".mmf")


class MusicTab(TabBase):
    LABEL = "Music"

    def __init__(self, parent, data):
        super().__init__(parent, data)

        # ---- Source toggle ------------------------------------------------
        top = ttk.Frame(self); top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Source:").pack(side="left")
        self.src_var = tk.StringVar(value="Mobile")
        for v in ("Mobile", "Android"):
            ttk.Radiobutton(top, text=v, variable=self.src_var, value=v,
                            command=self.refresh).pack(side="left", padx=4)
        ttk.Label(top, text=("(Mobile = MFi/.mld melodies in snd.dat across "
                             "all loaded chapters;  Android = snd.dat melodies "
                             "+ streamed ogg/mp3 in the .obb)")
                  ).pack(side="left", padx=8)

        # ---- Body: track list + info pane ---------------------------------
        body = ttk.Frame(self); body.pack(fill="both", expand=True, padx=6, pady=4)
        left = ttk.Frame(body); left.pack(side="left", fill="y")
        ttk.Label(left, text="Tracks").pack(anchor="w")
        self.lst = tk.Listbox(left, width=48, height=24, exportselection=False)
        self.lst.pack(side="left", fill="y")
        sb = ttk.Scrollbar(left, command=self.lst.yview); sb.pack(side="left", fill="y")
        self.lst.config(yscrollcommand=sb.set)
        self.lst.bind("<<ListboxSelect>>", lambda e: self._on_select())

        right = ttk.Frame(body); right.pack(side="left", fill="both", expand=True, padx=8)
        self.info = ScrolledText(right, height=12, wrap="word")
        self.info.pack(fill="both", expand=True)

        # ---- Action bar ---------------------------------------------------
        btns = ttk.Frame(self); btns.pack(fill="x", padx=6, pady=4)
        self.btn_save = ttk.Button(btns, text="Save .mld...", command=self._save,
                                   state="disabled")
        self.btn_save.pack(side="left", padx=2)
        self.btn_open = ttk.Button(btns, text="Open in default app",
                                   command=self._open, state="disabled")
        self.btn_open.pack(side="left", padx=2)
        self.btn_all = ttk.Button(btns, text="Export all...",
                                  command=self._export_all, state="disabled")
        self.btn_all.pack(side="left", padx=2)
        # Deferred: MFi5 -> MIDI conversion is not implemented yet, so this
        # stays disabled rather than emitting a fake/garbage .mid.
        self.btn_mid = ttk.Button(btns, text="Export .mid (deferred)",
                                  command=self._mid_deferred, state="disabled")
        self.btn_mid.pack(side="left", padx=2)
        ttk.Label(btns, text="(.mid: MFi5 event stream not yet decoded)",
                  foreground="#777").pack(side="left", padx=6)
        self.note = ttk.Label(btns, text="", foreground="#a00")
        self.note.pack(side="left", padx=12)

        # Each entry: {name, data, ext, fname, info}
        self.entries = []

    # -----------------------------------------------------------------------
    def on_data_change(self):
        self.refresh()

    def refresh(self):
        self.entries = []
        self.lst.delete(0, "end")
        self.info.delete("1.0", "end")
        self.btn_save.config(state="disabled")
        self.btn_open.config(state="disabled")
        self.btn_all.config(state="disabled")
        self.note.config(text="")

        if self.src_var.get() == "Mobile":
            self._load_mobile()
        else:
            self._load_android()

        for e in self.entries:
            self.lst.insert("end", e["name"])
        if self.entries:
            self.btn_all.config(state="normal")
        else:
            if not self.note.cget("text"):
                self.note.config(text="No audio tracks found in current sources.")

    # ---- loaders ----------------------------------------------------------
    def _add_entries(self, tracks, source):
        """Append parsed snd.dat SndEntry items under a source label."""
        for e in tracks:
            name = "%s   %s[%03d]   %s" % (source, e.bank_role, e.index, e.fmt)
            fname = "%s__%s_%03d%s" % (
                source.replace("/", "_"), e.bank_role, e.index, e.ext)
            extra = ""
            if e.fmt == "MFi":
                extra = ("MFi v5 (DoCoMo). Raw .mld is byte-exact; playback needs "
                         "an MFi-capable player/emulator.\n"
                         ".mid conversion is not yet implemented (MFi5 event "
                         "stream undecoded).\n")
            self.entries.append({
                "name": name,
                "data": e.data,
                "ext": e.ext,
                "fname": fname,
                "info": ("%s melody -- %s\n"
                         "Bank %d (%s), slot %d\n"
                         "Size: %d bytes\n"
                         "Magic: %r   Header: %s\n%s" % (
                             e.fmt, source, e.bank, e.bank_role, e.index,
                             len(e.data), e.data[:4],
                             e.data[:12].hex(" "), extra)),
            })

    def _load_mobile(self):
        found_any = False
        errs = []
        for slot, blob in self.data.find_in_sp_any_chapter("snd.dat"):
            found_any = True
            try:
                self._add_entries(parse_snd(blob), source=slot)
            except Exception as exc:
                errs.append("%s: %s" % (slot, exc))
        if not found_any:
            self.note.config(text="snd.dat not loaded -- load .sp file(s) "
                                  "containing it via the Files tab.")
        elif errs:
            self.note.config(text="parse error(s): " + "; ".join(errs))

    def _load_android(self):
        if "obb" not in self.data.archives_loaded():
            self.note.config(text=".obb not loaded -- Android audio lives "
                                  "inside the .obb.")
            return
        # (a) MFi melodies in the Android snd.dat (identical container layout).
        snd = self.data.in_obb("snd.dat")
        if snd:
            try:
                self._add_entries(parse_snd(snd), source="android/snd.dat")
            except Exception as exc:
                self.note.config(text="Android snd.dat parse error: %s" % exc)
        # (b) loose streamed audio assets (ogg/mp3/...).
        found = [(f, r) for f, r in self.data.list_obb_all()
                 if f.lower().endswith(_ANDROID_AUDIO_EXTS)]
        found.sort(key=lambda x: x[0].lower())
        for fname, raw in found:
            ext = "." + fname.rsplit(".", 1)[-1]
            self.entries.append({
                "name": fname,
                "data": raw,
                "ext": ext,
                "fname": fname.replace("/", "_"),
                "info": ("Android streamed audio asset\nPath: %s\n"
                         "Size: %d bytes\nFormat: %s\n" % (fname, len(raw), ext)),
            })
        if not self.entries:
            self.note.config(text="No audio found inside .obb "
                                  "(no snd.dat melodies, no ogg/mp3).")

    # ---- selection / single export ---------------------------------------
    def _on_select(self):
        sel = self.lst.curselection()
        if not sel:
            return
        e = self.entries[sel[0]]
        self.info.delete("1.0", "end")
        self.info.insert("1.0", e["info"])
        self.btn_save.config(state="normal")
        self.btn_open.config(state="normal")
        self.btn_save.config(text="Save %s..." % e["ext"])

    def _save(self):
        sel = self.lst.curselection()
        if not sel:
            return
        e = self.entries[sel[0]]
        path = filedialog.asksaveasfilename(
            defaultextension=e["ext"],
            initialfile=e["fname"],
            filetypes=[(e["ext"][1:].upper(), "*" + e["ext"]),
                       ("All files", "*.*")])
        if not path:
            return
        try:
            Path(path).write_bytes(e["data"])
            messagebox.showinfo("Saved", "Wrote %d bytes to:\n%s"
                                % (len(e["data"]), path))
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    def _export_all(self):
        if not self.entries:
            messagebox.showinfo("Export all", "No tracks loaded.")
            return
        dirpath = filedialog.askdirectory(
            title="Choose a folder to export all %d audio file(s) into"
                  % len(self.entries))
        if not dirpath:
            return
        base = Path(dirpath)
        n = err = 0
        for e in self.entries:
            try:
                (base / e["fname"]).write_bytes(e["data"])
                n += 1
            except Exception:
                err += 1
        msg = "Exported %d file(s) to:\n%s" % (n, base)
        if err:
            msg += "\n%d file(s) failed to write." % err
        messagebox.showinfo("Export all", msg)

    def _open(self):
        sel = self.lst.curselection()
        if not sel:
            return
        e = self.entries[sel[0]]
        try:
            tdir = tempfile.mkdtemp(prefix="ffd_audio_")
            p = Path(tdir) / e["fname"]
            p.write_bytes(e["data"])
            open_in_default_app(str(p))
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc))

    def _mid_deferred(self):
        # Unreachable while the button is disabled; kept for when MFi->MIDI
        # conversion is implemented.
        messagebox.showinfo(
            "MIDI conversion deferred",
            "These are MFi v5 melodies. Their per-track event stream is not "
            "yet decoded, so .mid conversion is not available. Use Save .mld "
            "to export the exact original melody.")
