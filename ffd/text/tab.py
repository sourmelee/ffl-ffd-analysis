"""Auto-extracted from the legacy ``ffd_toolkit.py`` mega-module.

Imports below cover the full set of names the original file made
available at module scope. Unused imports are kept rather than pruned
so the relocated class body remains byte-for-byte identical to the
original code; we apply only light tidy (a module docstring and
consolidated import block).
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path


from ..gui_stub import (
    tk, ttk, filedialog, messagebox, ScrolledText,
)
from ..monsters.parser import (
    parse_enemies_mobile, parse_monsters_android,
    parse_bem, decode_monster_body,
)
from ..items.parser import parse_items_mobile, parse_items_android
from ..jobs.parser  import parse_jobs_mobile, parse_jobs_android
from ..abilities.parser import (
    parse_magic_android, parse_passive_abilities_android,
    parse_command_abilities_android,
)
from ..text.parser    import MESSAGE_SECTION_LABELS, parse_message, parse_msd
from ..music.parser   import parse_resbin, parse_audio_names_resbin
from ..gui_core.base   import TabBase



# ============================================================================
# TAB — TEXT (message.dat sections, names, audio, etc.)
# ============================================================================

class TextTab(TabBase):
    LABEL = "Text"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._sources = OrderedDict()    # label -> list[str] (or callable)
        self._build()
        self.on_data_change()

    def _build(self):
        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=8)

        # Left: source picker
        leftf = ttk.Frame(body); body.add(leftf, weight=1)
        ttk.Label(leftf, text="Text source:").pack(anchor="w")
        list_holder = ttk.Frame(leftf); list_holder.pack(fill="both",
                                                          expand=True)
        self.lst = tk.Listbox(list_holder, exportselection=False,
                              font=("TkDefaultFont", 9))
        sb = ttk.Scrollbar(list_holder, orient="vertical",
                           command=self.lst.yview)
        self.lst.configure(yscrollcommand=sb.set)
        self.lst.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.lst.bind("<<ListboxSelect>>", self._on_select)

        # Right: text + search
        rightf = ttk.Frame(body); body.add(rightf, weight=4)
        searchbar = ttk.Frame(rightf); searchbar.pack(fill="x")
        ttk.Label(searchbar, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        ent = ttk.Entry(searchbar, textvariable=self.search_var)
        ent.pack(side="left", fill="x", expand=True, padx=4)
        ent.bind("<Return>", lambda e: self._do_search())
        ttk.Button(searchbar, text="Find next",
                   command=self._do_search).pack(side="left", padx=2)
        ttk.Button(searchbar, text="Save TXT…",
                   command=self._save).pack(side="left", padx=2)

        self.txt = ScrolledText(rightf, wrap="word",
                                font=("TkDefaultFont", 10))
        self.txt.pack(fill="both", expand=True)

    def on_data_change(self):
        self._sources.clear()
        self.lst.delete(0, "end")

        # message.dat — split into 16 sections per chapter source
        for slot, blob in self.data.find_in_sp_any_chapter("message.dat"):
            sections = parse_message(blob)
            for i, sec in enumerate(sections):
                label_name = (MESSAGE_SECTION_LABELS[i]
                              if i < len(MESSAGE_SECTION_LABELS)
                              else f"section {i}")
                key = f"[{slot}] message.dat · {i:02d}: {label_name}"
                self._sources[key] = list(sec)
            break  # one chapter is enough — sections cover the whole game

        # Ability names from bem.dat (use largest)
        best, best_slot = [], None
        for slot, blob in self.data.find_in_sp_any_chapter("bem.dat"):
            ab = parse_bem(blob)
            if len(ab) > len(best):
                best, best_slot = ab, slot
        if best:
            key = f"[{best_slot}] abilities (bem.dat)"
            self._sources[key] = [f"{i:03d}  {n}"
                                  for i, n in enumerate(best)]

        # res.bin audio names from .obb
        if self.data.obb_files and "res.bin" in self.data.obb_files:
            blocks = parse_resbin(self.data.obb_files["res.bin"])
            an = parse_audio_names_resbin(blocks)
            if an:
                self._sources["[obb] BGM/SFX names (res.bin)"] = \
                    [f"{i:03d}  {n}" for i, n in enumerate(an)]

        # Mobile enemy names + descriptions
        boot = self.data.boot_data_mobile()
        if boot:
            ene = parse_enemies_mobile(boot)
            self._sources["[mobile] enemy names + descriptions"] = \
                [f"{e['id']:03d}  {e['name']}\n      {e['desc']}"
                 for e in ene]

        # ---- English text from .obb .msd files ----------------------------
        if self.data.obb_files:
            obb = self.data.obb_files

            # msg0.msd … msg15.msd — English chapter dialogue
            # Each file corresponds to one dialogue section (same order as
            # message.dat sections 0-15).
            msd_dialogue = {}
            for k in obb:
                name = Path(k).name
                if name.startswith("msg") and name.endswith(".msd"):
                    try:
                        idx = int(name[3:-4])
                        msd_dialogue[idx] = obb[k]
                    except ValueError:
                        pass
            for idx in sorted(msd_dialogue):
                sections = parse_msd(msd_dialogue[idx])
                for si, sec in enumerate(sections):
                    if not sec:
                        continue
                    label_name = (MESSAGE_SECTION_LABELS[idx]
                                  if idx < len(MESSAGE_SECTION_LABELS)
                                  else f"section {idx}")
                    key = f"[obb/EN] msg{idx}.msd · {label_name}"
                    self._sources[key] = [f"{i:03d}  {s}"
                                          for i, s in enumerate(sec)]

            # bem.msd — English ability names
            bem_msd = obb.get("bem.msd")
            if bem_msd:
                sections = parse_msd(bem_msd)
                all_strs = [s for sec in sections for s in sec]
                if all_strs:
                    self._sources["[obb/EN] abilities (bem.msd)"] = \
                        [f"{i:03d}  {s}" for i, s in enumerate(all_strs)]

            # system_message.msd, sysmes.msd, dbgmes.msd, sysanm-adjacent
            for fname in ("system_message.msd", "sysmes.msd",
                          "dbgmes.msd", "bem.msd"):
                blob = obb.get(fname)
                if blob and fname != "bem.msd":
                    sections = parse_msd(blob)
                    all_strs = [s for sec in sections for s in sec]
                    if all_strs:
                        label = fname.replace(".msd", "").replace("_", " ")
                        self._sources[f"[obb/EN] {label}"] = \
                            [f"{i:03d}  {s}" for i, s in enumerate(all_strs)]
        and_boot = self.data.boot_data_android()
        if and_boot:
            # Bestiary (full records with HP + stats from libjniproxy.so).
            # parse_monsters_android returns bare {id, name, body} records;
            # decode_monster_body extracts max_hp + other stats from the
            # 64-byte body. See monsters/parser.py for the body schema.
            and_monsters = parse_monsters_android(and_boot)
            if and_monsters:
                rows = []
                for i, m in enumerate(and_monsters):
                    if not m:
                        rows.append(f"{i:03d}  (deleted slot)")
                        continue
                    body = m.get("body")
                    if body:
                        decoded = decode_monster_body(body)
                        hp = decoded.get("max_hp", "?")
                    else:
                        hp = "?"
                    rows.append(f"{i:03d}  {m['name']}   HP={hp}")
                self._sources["[android] monsters (name + HP)"] = rows

            # Items / Magic / Abilities / Jobs — all use the same
            # (pascal name + pascal desc + body) format. Parsers from
            # ffd_toolkit decode each section's body size correctly.
            for label, parser in (
                ("items",   parse_items_android),
                ("magic",   parse_magic_android),
                ("passive abilities",  parse_passive_abilities_android),
                ("command abilities",  parse_command_abilities_android),
                ("jobs",    parse_jobs_android),
            ):
                recs = parser(and_boot)
                if not recs:
                    continue
                self._sources[f"[android] {label}"] = [
                    f"{i:03d}  {r['name']}"
                    + (f"\n      {r['desc']}" if r and r["desc"] else "")
                    if r else f"{i:03d}  (deleted slot)"
                    for i, r in enumerate(recs)
                ]

        # Item names
        if boot:
            items = parse_items_mobile(boot)
            self._sources["[mobile] items"] = \
                [f"{it['id']:03d}  {it['name']}\n      {it['desc']}"
                 for it in items]

        # Job names
        if boot:
            jobs = parse_jobs_mobile(boot)
            self._sources["[mobile] jobs"] = \
                [f"{j['id']:03d}  {j['name']}\n      {j['desc']}"
                 for j in jobs]

        for k in self._sources:
            self.lst.insert("end", k)

        if not self._sources:
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0", "No text data available. Load a "
                            ".sp file or .obb to populate.")

    def _on_select(self, _ev=None):
        sel = self.lst.curselection()
        if not sel: return
        key = self.lst.get(sel[0])
        lst = self._sources.get(key, [])
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", "\n".join(lst) if lst else "(empty)")

    def _do_search(self):
        q = self.search_var.get()
        if not q: return
        # Continue from current insertion if possible
        start = self.txt.index("insert")
        idx = self.txt.search(q, start, nocase=True, stopindex="end")
        if not idx:
            idx = self.txt.search(q, "1.0", nocase=True, stopindex="end")
            if not idx:
                messagebox.showinfo("Search", f"Not found: {q}")
                return
        end = f"{idx}+{len(q)}c"
        self.txt.tag_remove("hl", "1.0", "end")
        self.txt.tag_add("hl", idx, end)
        self.txt.tag_configure("hl", background="#fffa8a")
        self.txt.mark_set("insert", end)
        self.txt.see(idx)

    def _save(self):
        sel = self.lst.curselection()
        if not sel: return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        Path(path).write_text(self.txt.get("1.0", "end"), encoding="utf-8")


# =============================================================================
# Music Tab
# =============================================================================
