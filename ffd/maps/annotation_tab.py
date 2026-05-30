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
    tk, ttk, messagebox,
)
from ..maps.mobile import (
    parse_mpkh_index,
)
from ..maps.mc_overrides import (
    map_key, bucket_key,
)
from ..data.ffdata     import FFData
from ..gui_core.base   import TabBase



# =============================================================================
# Map Annotation Tab
# =============================================================================
class MapAnnotationTab(TabBase):
    """
    Walk through every Android map and assign its primary mc_id + variant.
    Persists to mc_overrides.json next to the loaded .obb.
    """
    LABEL = "Map Annotations"

    def __init__(self, parent, data_or_app):
        from collections import OrderedDict
        if isinstance(data_or_app, FFData):
            data = data_or_app
        else:
            data = data_or_app.data
        super().__init__(parent, data)
        self._android_maps = OrderedDict()
        self._buckets = OrderedDict()
        self._tree = None
        self._build()
        self.on_data_change()

    def _build(self):
        top = ttk.Frame(self); top.pack(fill="x", padx=6, pady=4, side="top")
        self._path_lbl = ttk.Label(top, text="(no obb loaded)", foreground="#666")
        self._path_lbl.pack(side="left")
        ttk.Button(top, text="Reload from disk", command=self._reload).pack(side="left", padx=8)
        ttk.Button(top, text="Save", command=self._save).pack(side="right", padx=4)
        pane = ttk.Panedwindow(self, orient="horizontal"); pane.pack(fill="both", expand=True, padx=6, pady=4)
        left = ttk.Frame(pane)
        ttk.Label(left, text="(chunk[18], chunk[5]) buckets:").pack(anchor="w")
        self._tree = ttk.Treeview(left, columns=("key", "mc", "var", "count", "conf"),
                                   show="tree headings", selectmode="browse")
        self._tree.heading("#0", text=""); self._tree.column("#0", width=30)
        self._tree.heading("key", text="key"); self._tree.column("key", width=160)
        self._tree.heading("mc", text="mc"); self._tree.column("mc", width=50)
        self._tree.heading("var", text="var"); self._tree.column("var", width=40)
        self._tree.heading("count", text="# maps"); self._tree.column("count", width=60)
        self._tree.heading("conf", text="conf"); self._tree.column("conf", width=60)
        tsb = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=tsb.set)
        self._tree.pack(side="left", fill="both", expand=True); tsb.pack(side="left", fill="y")
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self._tree.bind("<<TreeviewOpen>>", lambda e: self._on_open())
        pane.add(left)
        right = ttk.Frame(pane)
        self._info_lbl = ttk.Label(right, text="(select a bucket or map)", wraplength=350)
        self._info_lbl.pack(anchor="w", pady=4)
        edit = ttk.LabelFrame(right, text="Override mc_id / variant"); edit.pack(fill="x", pady=4)
        ttk.Label(edit, text="mc_id:").grid(row=0, column=0, padx=4, sticky="w")
        self._mc_var = tk.StringVar(value="0")
        ttk.Spinbox(edit, from_=0, to=255, textvariable=self._mc_var, width=6).grid(row=0, column=1)
        ttk.Label(edit, text="variant:").grid(row=0, column=2, padx=4, sticky="w")
        self._var_var = tk.StringVar(value="0")
        ttk.Spinbox(edit, from_=0, to=3, textvariable=self._var_var, width=4).grid(row=0, column=3)
        self._confirmed_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(edit, text="user-confirmed", variable=self._confirmed_var).grid(row=0, column=4, padx=8)
        ttk.Button(edit, text="Apply to selected", command=self._apply).grid(row=1, column=0, columnspan=3, pady=4)
        ttk.Button(edit, text="Clear (use parent)", command=self._clear_selected).grid(row=1, column=3, columnspan=2, padx=4, pady=4)
        ttk.Label(right, text="Tip: use the Maps tab to render with the current override and confirm visually.",
                  foreground="#444", wraplength=350).pack(anchor="w", pady=8)
        pane.add(right)

    def on_data_change(self):
        obb_files = getattr(self.data, "obb_files", None)
        if obb_files:
            path = self.data.mc_overrides_path()
            self._path_lbl.configure(text=f"mc_overrides → {path}", foreground="#444")
            self._reload()
        else:
            self._path_lbl.configure(text="(no obb loaded)", foreground="#a00")

    def _reload(self):
        self._collect_android_maps()
        self._rebuild_tree()

    def _save(self):
        try:
            self.data.save_mc_overrides()
            messagebox.showinfo("Saved", f"Wrote {self.data.mc_overrides_path()}")
        except Exception as exc:
            messagebox.showerror("Save failed", f"Could not write mc_overrides.json\n{exc}")

    def _collect_android_maps(self):
        from collections import OrderedDict
        self._android_maps = OrderedDict(); self._buckets = OrderedDict()
        obb_files = getattr(self.data, "obb_files", {}) or {}
        mpkh_keys = [k for k in obb_files if Path(k).name.startswith("mpkh")]
        for mpkh_key in sorted(mpkh_keys):
            mpkh_blob = obb_files[mpkh_key]
            try:
                packs = parse_mpkh_index(mpkh_blob)
            except Exception:
                continue
            stem = Path(mpkh_key).stem
            group = int("".join(c for c in stem if c.isdigit()) or "0")
            for pi, entries in enumerate(packs):
                pk_key = f"g{group}p{pi}"
                self._android_maps[pk_key] = entries
                for mid, entry in enumerate(entries if isinstance(entries, list) else []):
                    try:
                        off = entry.get("offset", 0) if isinstance(entry, dict) else 0
                        sz = entry.get("size", 0) if isinstance(entry, dict) else 0
                        blob = obb_files.get(next(k for k in obb_files if Path(k).name.startswith("mpk")
                                                   and f"{group}" in k), b"")
                        chunk = blob[off:off + min(sz, 64)] if isinstance(blob, (bytes, bytearray)) and sz else b""
                        if len(chunk) >= 19:
                            bk = bucket_key({"chunk18": chunk[18], "chunk5": chunk[5]})
                            self._buckets.setdefault(bk, []).append(
                                {"group": group, "pack": pi, "map_id": mid})
                    except Exception:
                        pass

    def _rebuild_tree(self):
        if self._tree is None: return
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        overrides = self.data.mc_overrides()
        by_group = overrides.get("by_group", {})
        self._tree.tag_configure("ok", foreground="#040")
        self._tree.tag_configure("missing", foreground="#a00")
        for gk, records in sorted(self._buckets.items(), key=lambda kv: -len(kv[1])):
            g_entry = by_group.get(gk, {})
            mc = g_entry.get("mc_id", "?"); var = g_entry.get("variant", "?")
            conf = g_entry.get("auto_confidence", 0)
            tag = "ok" if isinstance(mc, int) else "missing"
            confirmed = "✓ " if g_entry.get("user_confirmed") else ""
            iid = f"BUCKET:{gk}"
            self._tree.insert("", "end", iid=iid, text=confirmed, open=False,
                               values=(gk, str(mc), str(var), str(len(records)),
                                       f"{conf:.0f}" if isinstance(conf, float) else str(conf)),
                               tags=(tag,))
            self._tree.insert(iid, "end", iid=f"_PLH_{gk}", text="(loading...)")

    def _on_open(self):
        iid = self._tree.focus()
        if not iid.startswith("BUCKET:"): return
        children = self._tree.get_children(iid)
        if not any(c.startswith("_PLH_") for c in children): return
        for c in children: self._tree.delete(c)
        gk = iid[len("BUCKET:"):]
        overrides = self.data.mc_overrides(); by_map = overrides.get("by_map", {})
        records = self._buckets.get(gk, [])
        for r in records:
            g, pi, mid = r["group"], r["pack"], r["map_id"]
            mk = map_key({"group": g, "pack": pi, "map_id": mid})
            m_entry = by_map.get(mk, {})
            mc = m_entry.get("mc_id", "?"); var = m_entry.get("variant", "?")
            conf = m_entry.get("auto_confidence", 0)
            confirmed = "✓ " if m_entry.get("user_confirmed") else ""
            tag = "ok" if isinstance(mc, int) else "missing"
            self._tree.insert(iid, "end", iid=f"MAP:{g}/{pi}/{mid}",
                               text=confirmed,
                               values=(mk, str(mc), str(var), "",
                                       f"{conf:.0f}" if isinstance(conf, float) else ""),
                               tags=(tag,))

    def _selected_kind(self):
        iid = self._tree.focus()
        try:
            if iid.startswith("BUCKET:"): return ("bucket", iid[len("BUCKET:"):])
            if iid.startswith("MAP:"):
                g, p, m = (int(x) for x in iid[len("MAP:"):].split("/"))
                return ("map", g, p, m)
        except Exception:
            pass
        return None

    def _on_select(self):
        sel = self._selected_kind()
        overrides = self.data.mc_overrides()
        by_group = overrides.get("by_group", {}); by_map = overrides.get("by_map", {})
        if sel is None:
            self._info_lbl.configure(text="(select a bucket or map)"); return
        info_lines = []
        if sel[0] == "bucket":
            gk = sel[1]; records = self._buckets.get(gk, []); g_entry = by_group.get(gk, {})
            mc = g_entry.get("mc_id", "?"); var = g_entry.get("variant", "?")
            info_lines += [f"Bucket: {gk}", f"Maps in bucket: {len(records)}",
                           f"Current default: mc{mc} var{var}"]
            self._mc_var.set(str(mc) if isinstance(mc, int) else "0")
            self._var_var.set(str(var) if isinstance(var, int) else "0")
            self._confirmed_var.set(bool(g_entry.get("user_confirmed", False)))
        else:
            _, g, p, m = sel
            mk = map_key({"group": g, "pack": p, "map_id": m})
            m_entry = by_map.get(mk, {}); g_entry = {}
            info_lines += [f"Map: group={g} pack={p} map_id={m}",
                           f"Bucket default: mc{g_entry.get('mc_id','?')} var{g_entry.get('variant','?')}"]
            if m_entry:
                info_lines.append(f"Override: mc{m_entry.get('mc_id','?')} var{m_entry.get('variant','?')}")
            mc = m_entry.get("mc_id", 0); var = m_entry.get("variant", 0)
            self._mc_var.set(str(mc) if isinstance(mc, int) else "0")
            self._var_var.set(str(var) if isinstance(var, int) else "0")
            self._confirmed_var.set(bool(m_entry.get("user_confirmed", False)))
        self._info_lbl.configure(text="\n".join(info_lines))

    def _apply(self):
        sel = self._selected_kind()
        if sel is None: return
        try:
            mc_id = int(self._mc_var.get()); variant = int(self._var_var.get())
        except ValueError:
            messagebox.showerror("Bad value", "mc_id and variant must be ints"); return
        overrides = self.data.mc_overrides(); confirmed = bool(self._confirmed_var.get())
        if sel[0] == "bucket":
            overrides.setdefault("by_group", {})[sel[1]] = {
                "mc_id": mc_id, "variant": variant, "user_confirmed": confirmed}
        else:
            _, g, p, m = sel
            overrides.setdefault("by_map", {})[map_key({"group": g, "pack": p, "map_id": m})] = {
                "mc_id": mc_id, "variant": variant, "user_confirmed": confirmed}
        self.data.save_mc_overrides(); self._refresh_selected_row()

    def _clear_selected(self):
        sel = self._selected_kind()
        if sel is None: return
        overrides = self.data.mc_overrides()
        if sel[0] == "bucket":
            overrides.get("by_group", {}).pop(sel[1], None)
        else:
            _, g, p, m = sel
            overrides.get("by_map", {}).pop(map_key({"group": g, "pack": p, "map_id": m}), None)
        self.data.save_mc_overrides(); self._refresh_selected_row()

    def _refresh_selected_row(self):
        opened = [iid for iid in self._tree.get_children() if self._tree.item(iid, "open")]
        self._rebuild_tree()
        for iid in opened:
            if self._tree.exists(iid):
                self._on_open()
        self._on_select()


# =============================================================================
# Main application class
# =============================================================================
