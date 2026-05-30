"""Auto-extracted from the legacy ``ffd_toolkit.py`` mega-module.

Imports below cover the full set of names the original file made
available at module scope. Unused imports are kept rather than pruned
so the relocated class body remains byte-for-byte identical to the
original code; we apply only light tidy (a module docstring and
consolidated import block).
"""

from __future__ import annotations

from pathlib import Path


from ..gui_stub import (
    tk, ttk, filedialog, messagebox, ScrolledText,
)
from ..maps.mobile import (
    scan_mobile_mpk_chunks,
)
from ..tilesets.parser import (
    parse_mpk_index_mobile, flat_pack_index,
)
from ..events.mobile   import (
    disassemble_event_region,
)
from ..events.android  import (
    disassemble_android_event_pack, scan_android_event_packs,
)
from ..events.strings  import extract_sjis_strings
from ..gui_core.helpers import (
    _hex_dump,
)
from ..gui_core.base   import TabBase



# =============================================================================
# Event Script Tab
# =============================================================================
class EventScriptTab(TabBase):
    LABEL = "Event Scripts"

    def __init__(self, parent, data):
        super().__init__(parent, data)
        intro = ttk.Frame(self); intro.pack(fill="x", padx=6, pady=(6, 0))
        ttk.Label(intro, text=(
            "Event scripts encode NPC placement, dialogue, treasure, warps and "
            "cutscenes. Mobile stores them inline at the end of each map chunk "
            "(class_16.method_785); Android stores them in separate event packs "
            "inside the .obb (FieldClass::LoadEventData). Pick the platform on "
            "the left, then select a map / pack to disassemble."
        ), foreground="#444", wraplength=900).pack(anchor="w")
        top = ttk.Frame(self); top.pack(fill="x", padx=6, pady=2)
        ttk.Label(top, text="Source:").pack(side="left")
        self.src_var = tk.StringVar(value="Mobile")
        for val in ("Mobile", "Android"):
            ttk.Radiobutton(top, text=val, variable=self.src_var, value=val,
                            command=self._reload).pack(side="left", padx=2)
        self.note = ttk.Label(top, text="", foreground="#a00"); self.note.pack(side="right")
        pane = ttk.Panedwindow(self, orient="horizontal"); pane.pack(fill="both", expand=True, padx=6, pady=4)
        left = ttk.Frame(pane)
        ttk.Label(left, text="Maps with event-script regions:").pack(anchor="w")
        self.lst = tk.Listbox(left, selectmode="single", width=38)
        self.lst.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(left, command=self.lst.yview); sb.pack(side="left", fill="y")
        self.lst.config(yscrollcommand=sb.set)
        self.lst.bind("<<ListboxSelect>>", lambda e: self._on_select())
        self.info_lbl = ttk.Label(left, text="", font=("Courier", 8)); self.info_lbl.pack(anchor="w", pady=4)
        pane.add(left)
        right = ttk.Frame(pane)
        subnb = ttk.Notebook(right); subnb.pack(fill="both", expand=True)
        asm_f = ttk.Frame(subnb); subnb.add(asm_f, text="Disassembly")
        self.asm_txt = ScrolledText(asm_f, wrap="none", font=("Courier", 9)); self.asm_txt.pack(fill="both", expand=True)
        str_f = ttk.Frame(subnb); subnb.add(str_f, text="Extracted SJIS strings")
        self.str_txt = ScrolledText(str_f, wrap="word", font=("Courier", 9)); self.str_txt.pack(fill="both", expand=True)
        hex_f = ttk.Frame(subnb); subnb.add(hex_f, text="Hex dump")
        self.hex_txt = ScrolledText(hex_f, wrap="none", font=("Courier", 9)); self.hex_txt.pack(fill="both", expand=True)
        btn_row = ttk.Frame(right); btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Save script bytes (.bin)…", command=self._save_bin).pack(side="left", padx=4, pady=2)
        ttk.Button(btn_row, text="Save extracted strings (.txt)…", command=self._save_strings).pack(side="left", padx=4, pady=2)
        pane.add(right)
        self.entries = []

    def on_data_change(self):
        self._reload()

    def _reload(self):
        self.entries = []
        self.lst.delete(0, "end")
        self.hex_txt.delete("1.0", "end")
        self.str_txt.delete("1.0", "end")
        self.asm_txt.delete("1.0", "end")
        self.info_lbl.config(text="")
        self.note.config(text="")
        src = self.src_var.get() if hasattr(self, "src_var") else "Mobile"
        if src == "Android":
            self._populate_android()
        else:
            self._populate_mobile()

    def _populate_mobile(self):
        n_total = 0; n_with_script = 0
        sp_slots = getattr(self.data, "sp_slots", {}) or {}
        for slot, files in sorted(sp_slots.items()):
            if not files: continue
            # Without the boot_data → mpk index, scan_mobile_mpk_chunks can't
            # know each chunk's real (post-tile) length and so reports zero
            # event-script regions. Parse the index up front and pass it in,
            # exactly the way ExtractTab/MapTab do it.
            boot = files.get("boot_data.dat")
            try:
                mpk_index = (flat_pack_index(parse_mpk_index_mobile(boot))
                             if boot else {})
            except Exception:
                mpk_index = {}
            by_pack = {}
            for mid, (pi, off, sz) in mpk_index.items():
                by_pack.setdefault(pi, []).append((mid, off, sz))
            mpks = sorted(k for k in files if k.startswith("mpk") and k.endswith(".dat"))
            for mi, mpk_name in enumerate(mpks):
                mpk_blob = files[mpk_name]
                pack_entries = by_pack.get(mi)
                try:
                    for scan in scan_mobile_mpk_chunks(mpk_blob, pack_entries):
                        n_total += 1
                        script = scan.get("script_bytes", b"")
                        if script:
                            n_with_script += 1
                            parsed = scan.get("parsed", {}) or {}
                            name = parsed.get("name", "") if parsed else ""
                            sz = len(script)
                            mid = scan.get("map_id")
                            mid_label = f"m{mid:03d}" if mid is not None else f"@{scan.get('offset',0):x}"
                            label = f"[{slot}] {mpk_name} {mid_label}  ({name}  {sz} B)"
                            entry = dict(scan); entry["slot"] = slot; entry["mpk"] = mpk_name; entry["name"] = name
                            entry["platform"] = "mobile"
                            self.entries.append(entry)
                            self.lst.insert("end", label)
                except Exception:
                    pass
        if n_total == 0:
            self.note.config(text="No event-script regions found (0 maps scanned).")
        else:
            self.note.config(text=f"{n_with_script} / {n_total} mobile maps have script regions")

    def _populate_android(self):
        obb = getattr(self.data, "obb_files", None)
        if not obb:
            self.note.config(text="No .obb loaded — open one in the Files tab first.")
            return
        try:
            packs = scan_android_event_packs(obb)
        except Exception as exc:
            self.note.config(text=f"Android scan failed: {exc}")
            return
        n_total = len(obb); n_packs = len(packs); n_events = 0
        for p in packs:
            info = p["info"]
            n_events += len(info["events"])
            label = f"{p['name']}  ({info['event_count']} events, {len(p['blob'])} B)"
            entry = {
                "platform": "android",
                "name": p["name"],
                "obb_name": p["name"],
                "script_bytes": p["blob"],
                "android_info": info,
                "slot": "obb",
                "mpk": p["name"],
            }
            self.entries.append(entry)
            self.lst.insert("end", label)
        if not packs:
            self.note.config(
                text=f"No event packs detected in {n_total} obb files "
                     f"(heuristic: u32-BE offset → event_count header).")
        else:
            self.note.config(
                text=f"{n_packs} android event packs / {n_events} events "
                     f"(of {n_total} obb files)")

    def _on_select(self):
        sel = self.lst.curselection()
        if not sel: return
        e = self.entries[sel[0]]
        script = e.get("script_bytes", b"")
        platform = e.get("platform", "mobile")
        if platform == "android":
            info_dict = e.get("android_info") or {}
            info = (f"Platform: Android\n"
                    f"    OBB file: {e.get('obb_name', '?')}\n"
                    f"    EDO: 0x{info_dict.get('edo', 0):x}\n"
                    f"    Event count: {info_dict.get('event_count', 0)}\n"
                    f"    Total bytes: {len(script)} (0x{len(script):x})")
            dis_input = script
            dis_fn = disassemble_android_event_pack
        else:
            parsed = e.get("parsed", {}) or {}
            chunk = e.get("chunk", b"")
            info = (f"Platform: Mobile\n"
                    f"    Slot: {e.get('slot', '?')}\n"
                    f"    Pack: {e.get('mpk', '?')}\n"
                    f"    Map: {e.get('name', '?')}\n"
                    f"\nMap size: {parsed.get('w', '?')}\xd7{parsed.get('h', '?')} tiles"
                    f"    Tile data ends at: 0x{e.get('tile_end', 0):x}\n"
                    f"    Chunk bytes: {len(chunk)} (0x{len(chunk):x})\n"
                    f"    Post-tile script bytes: {len(script)} (0x{len(script):x})")
            # Mobile parse_mobile_event_region wants the FULL chunk because it
            # has to re-compute the event-start offset (tile data + attr-layer
            # bytes); passing only the post-tile slice mis-parses.
            dis_input = chunk if chunk else script
            dis_fn = disassemble_event_region
        self.info_lbl.config(text=info)
        self.hex_txt.delete("1.0", "end"); self.hex_txt.insert("1.0", _hex_dump(script))
        self.str_txt.delete("1.0", "end")
        strings = extract_sjis_strings(script)
        if strings:
            self.str_txt.insert("1.0", "\n".join(f"+0x{off:04x}: {s}" for off, s in strings))
        else:
            self.str_txt.insert("1.0", "(No length-prefixed Shift-JIS strings detected)")
        self.asm_txt.delete("1.0", "end")
        try:
            asm = dis_fn(dis_input)
        except Exception as exc:
            asm = f"[disassembly error: {exc}]"
        self.asm_txt.insert("1.0", asm)

    def _save_bin(self):
        sel = self.lst.curselection()
        if not sel: return
        e = self.entries[sel[0]]
        script = e.get("script_bytes", b""); name = e.get("name", "map")
        path = filedialog.asksaveasfilename(defaultextension=".bin",
                                            initialfile=f"{name}_script.bin",
                                            filetypes=[("Binary", "*.bin"), ("All files", "*.*")])
        if not path: return
        try:
            Path(path).write_bytes(script)
            messagebox.showinfo("Saved", f"Wrote {len(script)} bytes")
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    def _save_strings(self):
        sel = self.lst.curselection()
        if not sel: return
        e = self.entries[sel[0]]; name = e.get("name", "map")
        text = self.str_txt.get("1.0", "end")
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                            initialfile=f"{name}_strings.txt",
                                            filetypes=[("Text", "*.txt")])
        if path:
            Path(path).write_text(text, encoding="utf-8")


# =============================================================================
# Animation Tab
# =============================================================================
