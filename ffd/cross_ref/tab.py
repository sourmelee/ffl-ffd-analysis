"""Auto-extracted from the legacy ``ffd_toolkit.py`` mega-module.

Imports below cover the full set of names the original file made
available at module scope. Unused imports are kept rather than pruned
so the relocated class body remains byte-for-byte identical to the
original code; we apply only light tidy (a module docstring and
consolidated import block).
"""

from __future__ import annotations



from ..gui_stub import (
    tk, ttk, ScrolledText,
)
from ..images.ic import render_ic
from ..sprites.container import (
    parse_sprite_container,
)
from ..monsters.parser import (
    parse_enemies_mobile,
)
from ..characters.parser import parse_chara_set
from ..formats.form_bin import parse_form_bin
from ..gui_core.helpers import (
    format_element_bits, format_status_bits,
)
from ..gui_core.base   import TabBase



# =============================================================================
# Cross-Ref Tab
# =============================================================================
class CrossRefTab(TabBase):
    LABEL = "Cross-Ref"

    def __init__(self, parent, data):
        super().__init__(parent, data)
        top = ttk.Frame(self); top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Subject:").pack(side="left")
        self.subject_var = tk.StringVar(value="Enemies")
        for val in ("Enemies", "Characters"):
            ttk.Radiobutton(top, text=val, variable=self.subject_var, value=val,
                            command=self._reload).pack(side="left", padx=2)
        ttk.Label(top, text="    Filter:").pack(side="left", padx=(12, 0))
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *a: self._apply_filter())
        ttk.Entry(top, textvariable=self.filter_var, width=20).pack(side="left", padx=4)
        self.note = ttk.Label(top, text="", foreground="#a00"); self.note.pack(side="right")
        pane = ttk.Panedwindow(self, orient="horizontal"); pane.pack(fill="both", expand=True, padx=6, pady=4)
        left = ttk.Frame(pane)
        ttk.Label(left, text="Subjects:").pack(anchor="w")
        self.lst = tk.Listbox(left, selectmode="single", width=32)
        self.lst.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(left, command=self.lst.yview); sb.pack(side="left", fill="y")
        self.lst.config(yscrollcommand=sb.set)
        self.lst.bind("<<ListboxSelect>>", lambda e: self._on_select())
        pane.add(left)
        right = ttk.Frame(pane)
        spr_frame = ttk.LabelFrame(right, text="Sprite"); spr_frame.pack(fill="both", expand=True, pady=(0,4))
        self.spr_canvas = tk.Canvas(spr_frame, background="#222", width=200, height=200); self.spr_canvas.pack(fill="both", expand=True)
        stats_frame = ttk.LabelFrame(right, text="Stats"); stats_frame.pack(fill="both", expand=True, pady=(0,4))
        self.stats_txt = ScrolledText(stats_frame, height=10, wrap="word"); self.stats_txt.pack(fill="both", expand=True)
        forms_frame = ttk.LabelFrame(right, text="Appears in formations"); forms_frame.pack(fill="x")
        self.forms_txt = ScrolledText(forms_frame, height=5, wrap="word"); self.forms_txt.pack(fill="both", expand=True)
        pane.add(right)
        self.all_records = []; self.shown = []; self.sprite_cache = {}
        self.formations = []; self.enemies_by_sprite = {}
        self._ene_blob = None; self._chpk_blob = None; self._spr_photo = None

    def on_data_change(self):
        self._reload()

    def _reload(self):
        self.all_records = []; self.sprite_cache = {}; self.formations = []; self.enemies_by_sprite = {}
        self.lst.delete(0, "end"); self.spr_canvas.delete("all")
        self.stats_txt.delete("1.0", "end"); self.forms_txt.delete("1.0", "end")
        self.note.config(text="")
        if self.subject_var.get() == "Enemies":
            self._load_enemies()
        else:
            self._load_characters()
        self._apply_filter()

    def _load_enemies(self):
        bd = self.data.boot_data_mobile()
        if bd is None:
            self.note.config(text="boot_data.dat not found — load .sp slots."); return
        try:
            enemies = parse_enemies_mobile(bd)
        except Exception as exc:
            self.note.config(text=f"enemies parse failed: {exc}"); return
        for en in enemies:
            self.enemies_by_sprite.setdefault(en.get("sprite_id", -1), []).append(en)
        for slot, blob in self.data.find_in_sp_any_chapter("form.bin"):
            try: self.formations = parse_form_bin(blob)
            except Exception: pass
            break
        for slot, blob in self.data.find_in_sp_any_chapter("ene.dat"):
            self._ene_blob = blob; break
        for i, en in enumerate(enemies):
            nm = en.get("name", f"3d{i:03d}")
            self.all_records.append((f"{i:3d}  {nm}", {"type": "en", "dict": en, "idx": i}))
        ok = "OK" if self._ene_blob else "MISSING (need ene.dat)"
        self.note.config(text=f"{len(enemies)} enemies \xb7 {len(self.formations)} formations \xb7 sprites {ok}")

    def _load_characters(self):
        result = self.data.find_in_sp("chara_set.dat")
        if result is None:
            self.note.config(text="chara_set.dat not found."); return
        raw = result[1] if isinstance(result, tuple) else result
        try:
            chars = parse_chara_set(raw)
        except Exception as exc:
            self.note.config(text=f"chara_set parse failed: {exc}"); return
        for slot2, b2 in self.data.find_in_sp_any_chapter("chpk.dat"):
            self._chpk_blob = b2; break
        for i, ch in enumerate(chars):
            nm = ch.get("name", f"char_{i:2d}")
            self.all_records.append((f"{i:3d}  {nm}", {"type": "ch", "dict": ch, "idx": i}))
        ok = "OK" if self._chpk_blob else "MISSING (need chpk.dat)"
        self.note.config(text=f"{len(chars)} characters \xb7 sprites {ok}")

    def _apply_filter(self):
        q = self.filter_var.get().strip().lower()
        self.shown = []; self.lst.delete(0, "end")
        for i, (label, _) in enumerate(self.all_records):
            if not q or q in label.lower():
                self.shown.append(i); self.lst.insert("end", label)

    def _on_select(self):
        sel = self.lst.curselection()
        if not sel: return
        rec_idx = self.shown[sel[0]]; _, rec = self.all_records[rec_idx]
        if self.subject_var.get() == "Enemies":
            self._show_enemy(rec)
        else:
            self._show_character(rec)

    def _show_enemy(self, rec):
        en = rec["dict"]
        self.spr_canvas.delete("all")
        img = self._enemy_sprite_for(en.get("sprite_id", -1))
        if img:
            from PIL import ImageTk as _ITk3
            scale = min(200 / max(1, img.width), 200 / max(1, img.height), 3.0)
            disp = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), resample=0)
            self._spr_photo = _ITk3.PhotoImage(disp)
            self.spr_canvas.create_image(100, 100, anchor="center", image=self._spr_photo)
        else:
            self.spr_canvas.create_text(60, 30, text="(no sprite)", fill="#aaa")
        lines = [f"Name: {en.get('name', '?')}",
                 f"Sprite ID: {en.get('sprite_id', '?')}    Size: {en.get('size', '?')}",
                 f"    Level: {en.get('level', '?')}    AI: {en.get('ai_type', '?')}"]
        desc = en.get("description", "")
        if desc: lines.append(f"\nDescription: {desc}")
        lines.append("\nCombat stats:")
        for k in ("hp", "mp", "str", "spd", "int", "spr", "eva", "atk", "def", "matk", "mdef"):
            if k in en: lines.append(f"  {k}: {en[k]}")
        lines.append("\nAffinities:")
        lines.append(f"  Weak to:  {format_element_bits(en.get('element_weak', 0) or 0)}")
        lines.append(f"  Half:     {format_element_bits(en.get('element_half', 0) or 0)}")
        lines.append(f"  Null:     {format_element_bits(en.get('element_null', 0) or 0)}")
        lines.append(f"  Status immune: {format_status_bits(en.get('status_immune', 0) or 0)}")
        self.stats_txt.delete("1.0", "end"); self.stats_txt.insert("1.0", "\n".join(lines))
        idx = rec["idx"]
        form_lines = [str(d) for d in self.formations if isinstance(d, dict)
                      and any(str(idx) in str(v) for v in d.values())]
        self.forms_txt.delete("1.0", "end")
        self.forms_txt.insert("1.0", "\n".join(form_lines) if form_lines else "(none found)")

    def _enemy_sprite_for(self, sprite_id: int):
        if sprite_id in self.sprite_cache: return self.sprite_cache[sprite_id]
        if self._ene_blob is None: return None
        try:
            # parse_sprite_container yields (entry_idx, var, ic, raw_bytes)
            # — palette is already baked into ic, so render_ic takes no var.
            for (e_idx, var, ic, _raw) in parse_sprite_container(self._ene_blob):
                if e_idx == sprite_id and var == 0:
                    img = render_ic(ic).convert("RGBA")
                    self.sprite_cache[sprite_id] = img; return img
        except Exception:
            pass
        return None

    def _show_character(self, rec):
        ch = rec["dict"]
        self.spr_canvas.delete("all")
        f186 = ch.get("f186"); f190 = ch.get("f190"); img = None
        if self._chpk_blob and f186 is not None:
            try:
                # parse_sprite_container yields (entry_idx, var, ic, raw_bytes)
                # — palette is already baked into ic, so render_ic takes no var.
                # f186 = chpk entry id, f190 = palette/variant id.
                want_var = f190 if isinstance(f190, int) else 0
                fallback = None
                for (e_idx, var, ic, _raw) in parse_sprite_container(self._chpk_blob):
                    if e_idx != f186:
                        continue
                    if var == want_var:
                        img = render_ic(ic).convert("RGBA")
                        break
                    if fallback is None:
                        fallback = (var, ic)
                if img is None and fallback is not None:
                    var, ic = fallback
                    img = render_ic(ic).convert("RGBA")
            except Exception:
                pass
        if img:
            from PIL import ImageTk as _ITk4
            scale = min(200 / max(1, img.width), 200 / max(1, img.height), 3.0)
            disp = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), resample=0)
            self._spr_photo = _ITk4.PhotoImage(disp)
            self.spr_canvas.create_image(100, 100, anchor="center", image=self._spr_photo)
        else:
            self.spr_canvas.create_text(60, 30, text="(no sprite)", fill="#aaa")
        lines = [f"Name: {ch.get('name', '?')}",
                 f"chpk entry (f186): {ch.get('f186', '?')}    palette (f190): {ch.get('f190', '?')}",
                 f"    sprite form (f189): {ch.get('f189', '?')}"]
        for k, v in ch.items():
            if k in ("name", "f186", "f190", "f189"): continue
            if isinstance(v, (bytes, bytearray)):
                lines.append(f"{k}: <{len(v)} bytes>")
            else:
                lines.append(f"{k}: {v}")
        self.stats_txt.delete("1.0", "end"); self.stats_txt.insert("1.0", "\n".join(lines))
        self.forms_txt.delete("1.0", "end"); self.forms_txt.insert("1.0", "(no cross-reference found)")


# =============================================================================
# Map Annotation Tab
# =============================================================================
