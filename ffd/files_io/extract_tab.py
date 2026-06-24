"""Auto-extracted from the legacy ``ffd_toolkit.py`` mega-module.

Imports below cover the full set of names the original file made
available at module scope. Unused imports are kept rather than pruned
so the relocated class body remains byte-for-byte identical to the
original code; we apply only light tidy (a module docstring and
consolidated import block).
"""

from __future__ import annotations

import io
import threading
import traceback
from pathlib import Path
from typing import Optional

from PIL import Image

from ..gui_stub import (
    tk, ttk, filedialog, ScrolledText,
)
from ..binary import (
    be_u16, be_u32,
)
from ..images.ic import ICImage, render_ic
from ..sprites.container import (
    parse_sprite_container, extract_hidden_gifs, parse_bip,
)
from ..maps.mobile import (
    scan_mobile_mpk_chunks, parse_mpkh_index,
)
from ..maps.android import (
    parse_android_map_engine, parse_android_map_chunk,
)
from ..maps.mc_overrides import (
    map_key, lookup_primary_mc,
)
from ..tilesets.parser import (
    parse_mpk_index_mobile, flat_pack_index,
    MobileTilesetResolver,
)
from ..monsters.parser import (
    parse_enemies_mobile, parse_monsters_android,
    parse_enemy_names_android, parse_bem,
)
from ..items.parser import parse_items_mobile, parse_items_android
from ..jobs.parser  import parse_jobs_mobile, parse_jobs_android
from ..abilities.parser import (
    parse_magic_android, parse_passive_abilities_android,
    parse_command_abilities_android,
)
from ..text.parser    import MESSAGE_SECTION_LABELS, parse_message
from ..music.parser   import parse_snd, parse_resbin, parse_audio_names_resbin
from ..gui_core.base   import TabBase


# ----------------------------------------------------------------------------
# Extract-tab options table.
#
# Each row is:
#   (key, default_on, label, requires_mobile_sp, requires_obb, output_subdir)
#
# `output_subdir` is the RELATIVE folder under the user's chosen output
# directory. Anything per-slot or per-source (mobile / android) appends
# further subfolders at extract time. Names are kept in lowercase /
# underscore form to match the option key style and to be filesystem-safe.
# ----------------------------------------------------------------------------
EXTRACT_OPTIONS = [
    # --- Raw passthrough --------------------------------------------------
    ("sp_raw",        False, "Raw files from each .sp",                  True,  False, "raw/sp"),
    ("obb_raw",       False, "Raw files from .obb (extract ZIP)",        False, True,  "raw/obb"),

    # --- Sprite atlases (Mobile sources) ----------------------------------
    ("characters",    True,  "Character sprites (chpk → PNG)",            True,  False, "sprites/characters"),
    ("monsters",      True,  "Monster sprites (ene → PNG)",               True,  False, "sprites/monsters"),
    ("battle_bg",     True,  "Battle backgrounds (bg → PNG)",             True,  False, "sprites/battle_backgrounds"),
    ("field_eff",     True,  "Field effects (feimg → PNG)",               True,  False, "sprites/field_effects"),
    ("system",        True,  "System / UI images (img_etc → PNG)",        True,  False, "sprites/system"),
    ("battle_eff",    True,  "Battle effects (bip → PNG, 3 groups)",      True,  False, "sprites/battle_effects"),

    # --- Tilesets ---------------------------------------------------------
    ("tilesets_mob",  True,  "Tilesets from .sp cpk*.dat (PNG)",          True,  False, "tilesets/mobile"),
    ("tilesets_and",  False, "Tilesets from .obb (mc*.png copy)",         False, True,  "tilesets/android"),

    # --- Maps -------------------------------------------------------------
    ("maps_mob",      True,  "Mobile maps (rendered as PNG)",             True,  False, "maps/mobile"),
    ("maps_and",      False, "Android maps (rendered, requires .obb tilesets)", False, True, "maps/android"),
    ("maps_and_mob",  False, "Android maps rendered with MOBILE tilesets (cross-port preview)", True, True, "maps/android_mobile_tilesets"),

    # --- Audio ------------------------------------------------------------
    ("audio_snd",     True,  "Audio: MFi/MLD from snd.dat (Mobile + Android)", True, True, "audio"),

    # --- Text (Mobile sources) -------------------------------------------
    ("text_dialog",   True,  "Story text from message.dat (TXT)",         True,  False, "text/dialogue/mobile"),
    ("text_abilities",True,  "Ability names from bem.dat (TXT)",          True,  False, "text/abilities/mobile"),
    ("text_audio",    True,  "BGM/SFX names from res.bin (TXT)",          False, True,  "text/audio_names/android"),
    ("text_enemies",  True,  "Enemy names from boot_data (TXT)",          True,  True,  "text/enemies"),
    ("text_items",    True,  "Item list (TXT/CSV)",                       True,  False, "text/items/mobile"),
    ("text_jobs",     True,  "Job list (TXT/CSV)",                        True,  False, "text/jobs/mobile"),
    ("formations",    False, "Formations from form.bin (TXT)",            True,  False, "text/formations/mobile"),
    ("collision",     False, "Tile collision from capk.dat (TXT)",        True,  False, "text/collision/mobile"),

    # --- Text (Android boot_data — new in 2026-05-13 decoding pass) ------
    ("text_items_and",     True,  "Items (Android boot_data §5 → TSV)",        False, True, "text/items/android"),
    ("text_magic_and",     True,  "Magic / spells (Android §2 → TSV)",         False, True, "text/magic/android"),
    ("text_passive_and",   True,  "Passive abilities (Android §3 → TSV)",      False, True, "text/passive_abilities/android"),
    ("text_command_and",   True,  "Command abilities (Android §4 → TSV)",      False, True, "text/command_abilities/android"),
    ("text_jobs_and",      True,  "Jobs (Android §6 → TSV)",                   False, True, "text/jobs/android"),
    ("text_monsters_and",  True,  "Bestiary (Android §9 — name + HP + stats)", False, True, "text/monsters/android"),
]


class ExtractTab(TabBase):
    LABEL = "Extract"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._vars = {}
        self._build()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)
        ttk.Label(top, text=(
            "Tick the asset categories to extract, choose an output folder, "
            "and press Extract. Each option writes to its own type/name "
            "subfolder so outputs stay organized."),
            wraplength=800).pack(anchor="w")

        # Output folder picker
        outf = ttk.Frame(self)
        outf.pack(fill="x", padx=8, pady=4)
        ttk.Label(outf, text="Output folder:").pack(side="left")
        self.out_var = tk.StringVar(value=str(Path.home() / "ffd_extract"))
        ttk.Entry(outf, textvariable=self.out_var).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(outf, text="Choose…",
                   command=self._pick_out).pack(side="left")

        # Bulk-toggle row
        bulk = ttk.Frame(self)
        bulk.pack(fill="x", padx=8, pady=2)
        ttk.Button(bulk, text="Select all",
                   command=self._select_all).pack(side="left", padx=2)
        ttk.Button(bulk, text="Select none",
                   command=self._select_none).pack(side="left", padx=2)
        ttk.Button(bulk, text="Defaults",
                   command=self._select_defaults).pack(side="left", padx=2)

        # Checkbox grid
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=4)

        opt_frame = ttk.LabelFrame(body, text="Options")
        opt_frame.pack(side="left", fill="both", expand=True, padx=(0, 4))

        for i, opt in enumerate(EXTRACT_OPTIONS):
            key, default, label = opt[0], opt[1], opt[2]
            v = tk.BooleanVar(value=default)
            self._vars[key] = v
            cb = ttk.Checkbutton(opt_frame, text=label, variable=v)
            cb.grid(row=i // 2, column=i % 2, sticky="w", padx=6, pady=2)

        # Right: log / status
        log_frame = ttk.LabelFrame(body, text="Log")
        log_frame.pack(side="left", fill="both", expand=True, padx=(4, 0))
        self.log = ScrolledText(log_frame, height=20, wrap="word",
                                font=("TkFixedFont", 9))
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

        # Run button
        runf = ttk.Frame(self)
        runf.pack(fill="x", padx=8, pady=8)
        self.run_btn = ttk.Button(runf, text="Extract",
                                  command=self._extract)
        self.run_btn.pack(side="left")
        self.prog = ttk.Progressbar(runf, mode="indeterminate")
        self.prog.pack(side="left", fill="x", expand=True, padx=8)

    def _pick_out(self):
        d = filedialog.askdirectory(initialdir=self.out_var.get() or ".")
        if d:
            self.out_var.set(d)

    def _select_all(self):
        for v in self._vars.values(): v.set(True)
    def _select_none(self):
        for v in self._vars.values(): v.set(False)
    def _select_defaults(self):
        for opt in EXTRACT_OPTIONS:
            key, default = opt[0], opt[1]
            self._vars[key].set(default)

    @staticmethod
    def _option_subdir(option_key: str) -> str:
        """Look up the output_subdir for a given EXTRACT_OPTIONS key."""
        for opt in EXTRACT_OPTIONS:
            if opt[0] == option_key:
                return opt[5] if len(opt) >= 6 else option_key
        return option_key

    @staticmethod
    def _safe_filename_part(name: str, default: str = "_",
                            max_len: int = 80) -> str:
        """
        Make a string safe to use as one component of a filesystem path.

        Strips control characters and reserved characters on both Windows and
        POSIX (<>:"/\\|?* + newline/tab/null + control bytes 0x00-0x1F), then
        trims trailing dots/spaces (which Windows silently strips), and caps
        length. Empty result falls back to `default`.

        Used wherever filenames are built from in-game data (map names,
        scratchpad slot labels, etc.) — Japanese names that include line
        breaks like 'クリスタルの\\n神殿' or path separators are common in
        the source data and would otherwise crash `Path.save`.
        """
        if not name:
            return default
        bad = set('<>:"/\\|?*\n\r\t\0')
        out = "".join("_" if (c in bad or ord(c) < 0x20) else c
                       for c in name)
        out = out.rstrip(". ")
        if len(out) > max_len:
            out = out[:max_len].rstrip(". ")
        return out or default

    def _log(self, *parts):
        self.log.insert("end", " ".join(str(p) for p in parts) + "\n")
        self.log.see("end")
        self.log.update_idletasks()

    def _extract(self):
        outdir = Path(self.out_var.get())
        outdir.mkdir(parents=True, exist_ok=True)
        self.log.delete("1.0", "end")
        self.run_btn.configure(state="disabled")
        self.prog.start(40)

        def worker():
            try:
                self._do_extract(outdir)
                self._log("Done.")
            except Exception:
                self._log("ERROR:", traceback.format_exc())
            finally:
                self.prog.stop()
                self.run_btn.configure(state="normal")

        threading.Thread(target=worker, daemon=True).start()

    def _do_extract(self, outdir: Path):
        v   = lambda k: self._vars[k].get()
        sub = lambda k: outdir / self._option_subdir(k)
        # Helper: safely turn a slot label into a filesystem-friendly subdir
        # (strips reserved chars, control chars, newlines, trailing dots).
        slot_name = lambda s: self._safe_filename_part(
            s.replace(" ", "_"), default="slot")

        # ---- Raw passthrough ------------------------------------------------
        if v("sp_raw"):
            self._log("Extracting raw .sp contents…")
            root = sub("sp_raw")
            for slot, files in self.data.sp_slots.items():
                if not files:
                    continue
                d = root / slot_name(slot)
                d.mkdir(parents=True, exist_ok=True)
                for name, blob in files.items():
                    safe = self._safe_filename_part(name, default="_unnamed")
                    (d / safe).write_bytes(blob)
                self._log(f"  {slot}: {len(files)} files → {d}")

        if v("obb_raw") and self.data.obb_files:
            self._log("Extracting raw .obb contents…")
            d = sub("obb_raw")
            for name, blob in self.data.obb_files.items():
                p = d / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(blob)
            self._log(f"  {len(self.data.obb_files)} files → {d}")

        # ---- Sprite atlases (Mobile) ----------------------------------------
        # Each chapter scratchpad has its OWN copy of these data files with
        # chapter-specific content (different enemies, different field
        # effects, different battle backgrounds), so we extract every loaded
        # slot — the old `break` after the first slot dropped all later
        # chapters' sprites on the floor.
        sprite_specs = [
            ("characters", "chpk.dat"),
            ("monsters",   "ene.dat"),
            ("battle_bg",  "bg.dat"),
            ("field_eff",  "feimg.dat"),
            ("system",     "img_etc.dat"),
        ]
        for opt, fname in sprite_specs:
            if not v(opt):
                continue
            self._log(f"Extracting {opt} from {fname}…")
            total = 0
            total_gifs = 0
            for slot, blob in self.data.find_in_sp_any_chapter(fname):
                d = sub(opt) / slot_name(slot)
                d.mkdir(parents=True, exist_ok=True)
                count = 0
                try:
                    entries = list(parse_sprite_container(blob))
                except Exception as exc:
                    self._log(f"  {slot}: parse failed ({exc})")
                    continue
                for (e, var, ic, _raw) in entries:
                    img = render_ic(ic)
                    img.save(d / f"{e:03d}_{var:02d}.png")
                    count += 1
                # Universal-fallback pass: scan ALL entries for hidden GIFs.
                # The proprietary parsers (ic / sub-offset table) silently
                # skip entries that don't match their layout, but those
                # entries often contain ENGINE-WRAPPED ANIMATED GIFs (the
                # engine prepends ~variable bytes of anchor/hitbox/frame
                # metadata before the standard GIF89a stream). See Jack's
                # 2026-05-13 hex analysis: this pattern appears across all
                # sprite-container .dat archives, not just ene.dat.
                gif_count = 0
                gif_dir = d / "_gifs"
                for (gif_idx, hdr_size, gif_bytes) in extract_hidden_gifs(blob):
                    if not gif_dir.exists():
                        gif_dir.mkdir(parents=True, exist_ok=True)
                    (gif_dir / f"{gif_idx:03d}_hdr{hdr_size}.gif"
                     ).write_bytes(gif_bytes)
                    gif_count += 1
                if gif_count:
                    self._log(f"  {slot}: {count} sprites + "
                              f"{gif_count} hidden GIFs → {d}")
                else:
                    self._log(f"  {slot}: {count} sprites → {d}")
                total += count
                total_gifs += gif_count
            extra = f" (+ {total_gifs} hidden GIFs)" if total_gifs else ""
            self._log(f"  {opt} total across all chapters: {total}{extra}")

        if v("battle_eff"):
            self._log("Extracting battle effects from bip.dat…")
            total = 0
            total_gifs = 0
            for slot, blob in self.data.find_in_sp_any_chapter("bip.dat"):
                d = sub("battle_eff") / slot_name(slot)
                d.mkdir(parents=True, exist_ok=True)
                count = 0
                for (g, e, var, ic) in parse_bip(blob):
                    img = render_ic(ic)
                    img.save(d / f"g{g}_{e:03d}_{var:02d}.png")
                    count += 1
                # Universal GIF-scan pass: bip.dat is a 3-group container.
                # Scan each group's data block separately so entry indices
                # stay accurate per-group.
                gif_count = 0
                gif_dir = d / "_gifs"
                if len(blob) >= 16:
                    g_offs = [be_u32(blob, 0), be_u32(blob, 4),
                              be_u32(blob, 8)]
                    g_sentinel = be_u32(blob, 12)
                    bounds = g_offs + [g_sentinel if g_sentinel > g_offs[-1]
                                       else len(blob)]
                    for gi in range(3):
                        gstart = g_offs[gi]
                        gend   = (bounds[gi+1] if bounds[gi+1] > gstart
                                  else len(blob))
                        if gstart >= len(blob) or gstart >= gend:
                            continue
                        sub_blob = blob[gstart:gend]
                        for (gi_idx, hdr_size, gif_bytes) in \
                                extract_hidden_gifs(sub_blob):
                            if not gif_dir.exists():
                                gif_dir.mkdir(parents=True, exist_ok=True)
                            (gif_dir /
                             f"g{gi}_{gi_idx:03d}_hdr{hdr_size}.gif"
                             ).write_bytes(gif_bytes)
                            gif_count += 1
                if gif_count:
                    self._log(f"  {slot}: {count} effects + "
                              f"{gif_count} hidden GIFs → {d}")
                else:
                    self._log(f"  {slot}: {count} effects → {d}")
                total += count
                total_gifs += gif_count
            extra = f" (+ {total_gifs} hidden GIFs)" if total_gifs else ""
            self._log(f"  battle_eff total across all chapters: {total}{extra}")

        # ---- Tilesets ------------------------------------------------------
        # Use the same boot_data-driven cpk index that the map renderer uses
        # (via MobileTilesetResolver). The previous parse_sprite_container
        # path silently dropped entries with unrecognized layouts. This path
        # mirrors what the engine itself sees, so coverage matches what the
        # Mobile maps actually render with.
        if v("tilesets_mob"):
            self._log("Extracting tilesets from cpk index (boot_data §48)…")
            total = 0
            total_gifs = 0
            for slot, files in self.data.sp_slots.items():
                if not files: continue
                try:
                    res = MobileTilesetResolver(files)
                except Exception as exc:
                    self._log(f"  {slot}: resolver failed ({exc})")
                    continue
                if not res.cpk_index:
                    continue
                d = sub("tilesets_mob") / slot_name(slot)
                d.mkdir(parents=True, exist_ok=True)
                slot_count = 0
                for eid in sorted(res.cpk_index):
                    for pal in range(8):
                        img = res.get(eid, pal)
                        if img is None:
                            break
                        img.save(d / f"entry{eid:03d}_pal{pal}.png")
                        slot_count += 1
                # Universal GIF-scan pass — cpk*.dat files are sprite-style
                # containers too. Each cpk file gets its own _gifs subdir.
                gif_count = 0
                gif_dir = d / "_gifs"
                for cpk_name, cpk_blob in sorted(res.cpk_files.items()):
                    sub_gif_dir = gif_dir / f"cpk{cpk_name}"
                    for (g_idx, hdr_size, gif_bytes) in \
                            extract_hidden_gifs(cpk_blob):
                        if not sub_gif_dir.exists():
                            sub_gif_dir.mkdir(parents=True, exist_ok=True)
                        (sub_gif_dir / f"{g_idx:03d}_hdr{hdr_size}.gif"
                         ).write_bytes(gif_bytes)
                        gif_count += 1
                if gif_count:
                    self._log(f"  {slot}: {slot_count} tileset images + "
                              f"{gif_count} hidden GIFs → {d}")
                else:
                    self._log(f"  {slot}: {slot_count} tileset images → {d}")
                total += slot_count
                total_gifs += gif_count
            extra = f" (+ {total_gifs} hidden GIFs)" if total_gifs else ""
            self._log(f"  tilesets_mob total across all chapters: "
                      f"{total}{extra}")

        if v("tilesets_and") and self.data.obb_files:
            self._log("Copying Android tilesets (mc*.png) from .obb…")
            d = sub("tilesets_and")
            d.mkdir(parents=True, exist_ok=True)
            count = 0
            for name, blob in self.data.obb_files.items():
                if Path(name).name.startswith("mc") \
                   and name.endswith(".png"):
                    (d / Path(name).name).write_bytes(blob)
                    count += 1
            self._log(f"  {count} tilesets → {d}")

        # ---- Maps ----------------------------------------------------------
        if v("maps_mob"):
            self._log("Rendering mobile maps…")
            d = sub("maps_mob"); d.mkdir(parents=True, exist_ok=True)
            count = self._extract_maps_mobile(d)
            self._log(f"  {count} maps rendered → {d}")

        if v("maps_and") and self.data.obb_files:
            self._log("Rendering Android maps…")
            d = sub("maps_and"); d.mkdir(parents=True, exist_ok=True)
            try:
                count = self._extract_maps_android(d)
                self._log(f"  {count} maps rendered → {d}")
            except Exception as e:
                self._log(f"  android map render failed: {e}")

        if (v("maps_and_mob") and self.data.obb_files
                and any(self.data.sp_slots.values())):
            self._log("Rendering Android maps with MOBILE tilesets "
                       "(cross-port preview)…")
            d = sub("maps_and_mob"); d.mkdir(parents=True, exist_ok=True)
            try:
                count = self._extract_maps_android(d, mobile_tilesets=True)
                self._log(f"  {count} maps rendered → {d}")
            except Exception as e:
                self._log(f"  android map (mobile ts) render failed: {e}")

        # ---- Audio ---------------------------------------------------------
        if v("audio_snd"):
            self._log("Extracting audio (MFi/MLD) from snd.dat…")
            total = 0
            for slot, blob in self.data.find_in_sp_any_chapter("snd.dat"):
                d = sub("audio_snd") / slot_name(slot)
                d.mkdir(parents=True, exist_ok=True)
                tracks = parse_snd(blob)
                for e in tracks:
                    (d / f"{e.bank_role}_{e.index:03d}{e.ext}").write_bytes(e.data)
                self._log(f"  {slot}: {len(tracks)} tracks → {d}")
                total += len(tracks)
            # Android: the .obb ships the same MFi container at snd.dat
            # (identical bank layout), so reuse the same parser + naming.
            snd_and = self.data.in_obb("snd.dat")
            if snd_and:
                d = sub("audio_snd") / "android"
                d.mkdir(parents=True, exist_ok=True)
                tracks = parse_snd(snd_and)
                for e in tracks:
                    (d / f"{e.bank_role}_{e.index:03d}{e.ext}").write_bytes(e.data)
                self._log(f"  android: {len(tracks)} tracks → {d}")
                total += len(tracks)
            self._log(f"  audio total across all sources: {total}")

        # ---- Text — Mobile sources -----------------------------------------
        if v("text_dialog"):
            self._log("Extracting message.dat dialogue…")
            for slot, blob in self.data.find_in_sp_any_chapter("message.dat"):
                sections = parse_message(blob)
                d = sub("text_dialog") / slot_name(slot)
                d.mkdir(parents=True, exist_ok=True)
                for i, sec in enumerate(sections):
                    label = (MESSAGE_SECTION_LABELS[i]
                             if i < len(MESSAGE_SECTION_LABELS)
                             else f"section_{i}")
                    safe = self._safe_filename_part(
                        label.replace("/", "-").replace(" ", "_"),
                        default=f"section_{i}")
                    (d / f"{i:02d}_{safe}.txt").write_text(
                        "\n".join(sec), encoding="utf-8")
                self._log(f"  {slot}: {sum(len(s) for s in sections)} strings → {d}")

        if v("text_abilities"):
            self._log("Extracting ability names from bem.dat…")
            best_slot, best_abi = None, []
            for slot, blob in self.data.find_in_sp_any_chapter("bem.dat"):
                ab = parse_bem(blob)
                if len(ab) > len(best_abi):
                    best_slot, best_abi = slot, ab
            if best_abi:
                d = sub("text_abilities"); d.mkdir(parents=True, exist_ok=True)
                (d / "abilities.txt").write_text(
                    "\n".join(f"{i:03d}\t{n}"
                             for i, n in enumerate(best_abi)),
                    encoding="utf-8")
                self._log(f"  {best_slot}: {len(best_abi)} abilities → {d}")

        if v("text_audio") and self.data.obb_files:
            self._log("Extracting BGM/SFX names from res.bin…")
            res = self.data.in_obb("res.bin")
            if res:
                blocks = parse_resbin(res)
                names = parse_audio_names_resbin(blocks)
                d = sub("text_audio"); d.mkdir(parents=True, exist_ok=True)
                (d / "audio_names.txt").write_text(
                    "\n".join(f"{i:03d}\t{n}" for i, n in enumerate(names)),
                    encoding="utf-8")
                self._log(f"  {len(names)} audio labels → {d}")

        if v("text_enemies"):
            self._log("Extracting enemy names…")
            d = sub("text_enemies"); d.mkdir(parents=True, exist_ok=True)
            mob = self.data.boot_data_mobile()
            if mob:
                dm = d / "mobile"; dm.mkdir(parents=True, exist_ok=True)
                ene = parse_enemies_mobile(mob)
                (dm / "enemies_mobile.txt").write_text(
                    "\n".join(f"{e['id']:03d}\t{e['name']}\tHP={e['max_hp']}"
                             f"\tATK={e['attack']}\tDEF={e['defense']}"
                             f"\tEXP={e['exp']}\tGil={e['gil']}"
                             for e in ene),
                    encoding="utf-8")
                self._log(f"  mobile: {len(ene)} → {dm}")
            and_ = self.data.boot_data_android()
            if and_:
                da = d / "android"; da.mkdir(parents=True, exist_ok=True)
                ene = parse_enemy_names_android(and_)
                (da / "enemies_android.txt").write_text(
                    "\n".join(f"{i:03d}\t{n}" for i, n in enumerate(ene)),
                    encoding="utf-8")
                self._log(f"  android: {len(ene)} → {da}")

        if v("text_items"):
            self._log("Extracting items (Mobile)…")
            mob = self.data.boot_data_mobile()
            if mob:
                items = parse_items_mobile(mob)
                d = sub("text_items"); d.mkdir(parents=True, exist_ok=True)
                # Fields from parse_items_mobile: id, name, desc, then a
                # variable schema. Dump as TSV preserving every dict key so
                # callers don't crash on schema drift.
                if items:
                    keys = list(items[0].keys())
                    rows = ["\t".join(keys)]
                    for it in items:
                        rows.append("\t".join(str(it.get(k, "")) for k in keys))
                    (d / "items.tsv").write_text("\n".join(rows),
                                                  encoding="utf-8")
                self._log(f"  {len(items)} items → {d}")

        if v("text_jobs"):
            self._log("Extracting jobs (Mobile)…")
            mob = self.data.boot_data_mobile()
            if mob:
                jobs = parse_jobs_mobile(mob)
                d = sub("text_jobs"); d.mkdir(parents=True, exist_ok=True)
                if jobs:
                    keys = list(jobs[0].keys())
                    rows = ["\t".join(keys)]
                    for jb in jobs:
                        rows.append("\t".join(str(jb.get(k, "")) for k in keys))
                    (d / "jobs.tsv").write_text("\n".join(rows),
                                                 encoding="utf-8")
                self._log(f"  {len(jobs)} jobs → {d}")

        if v("formations"):
            self._log("Extracting form.bin formations…")
            for slot, blob in self.data.find_in_sp_any_chapter("form.bin"):
                d = sub("formations") / slot_name(slot)
                d.mkdir(parents=True, exist_ok=True)
                rows = self._dump_formations(blob)
                (d / "formations.txt").write_text("\n".join(rows),
                                                   encoding="utf-8")
                self._log(f"  {slot}: {len(rows)} formations → {d}")

        if v("collision"):
            self._log("Extracting capk.dat collision…")
            for slot, blob in self.data.find_in_sp_any_chapter("capk.dat"):
                d = sub("collision") / slot_name(slot)
                d.mkdir(parents=True, exist_ok=True)
                rows = self._dump_collision(blob)
                (d / "collision.txt").write_text("\n".join(rows),
                                                  encoding="utf-8")
                self._log(f"  {slot}: {len(rows)} rows → {d}")

        # ---- Text — Android boot_data sections -----------------------------
        and_boot = self.data.boot_data_android()
        and_text_specs = [
            ("text_items_and",    "items.tsv",
             parse_items_android,                "items"),
            ("text_magic_and",    "magic.tsv",
             parse_magic_android,                "magic / spells"),
            ("text_passive_and",  "passive_abilities.tsv",
             parse_passive_abilities_android,    "passive abilities"),
            ("text_command_and",  "command_abilities.tsv",
             parse_command_abilities_android,    "command abilities"),
            ("text_jobs_and",     "jobs.tsv",
             parse_jobs_android,                 "jobs"),
        ]
        for opt_key, fname, parser, label in and_text_specs:
            if not v(opt_key) or not and_boot:
                continue
            self._log(f"Extracting {label} (Android)…")
            recs = parser(and_boot)
            d = sub(opt_key); d.mkdir(parents=True, exist_ok=True)
            rows = ["index\tname\tdescription\tbody_hex"]
            for i, r in enumerate(recs):
                if r is None:
                    rows.append(f"{i:04d}\t(deleted)\t\t")
                else:
                    body_hex = r.get("body", b"").hex(" ")
                    rows.append(f"{i:04d}\t{r['name']}\t{r['desc']}\t{body_hex}")
            (d / fname).write_text("\n".join(rows), encoding="utf-8")
            real = sum(1 for r in recs if r)
            self._log(f"  {real}/{len(recs)} records → {d}")

        if v("text_monsters_and") and and_boot:
            self._log("Extracting bestiary (Android)…")
            mons = parse_monsters_android(and_boot)
            d = sub("text_monsters_and"); d.mkdir(parents=True, exist_ok=True)
            rows = ["index\tname\tsprite_id\tfield9\thp\tstat_b\tstat_c\t"
                    "field14\tskills_hex"]
            for i, m in enumerate(mons):
                if m is None:
                    rows.append(f"{i:04d}\t(deleted)\t\t\t\t\t\t\t")
                else:
                    rows.append(
                        f"{i:04d}\t{m['name']}\t{m['sprite_id']}\t"
                        f"{m['field9']}\t{m['max_hp']}\t{m['stat_b']}\t"
                        f"{m['stat_c']}\t{m['field14']}\t"
                        f"{m['skills'].hex(' ')}"
                    )
            (d / "monsters.tsv").write_text("\n".join(rows), encoding="utf-8")
            real = sum(1 for m in mons if m and m.get("name"))
            self._log(f"  {real}/{len(mons)} monsters → {d}")

    def _dump_formations(self, blob: bytes):
        if len(blob) < 2:
            return []
        n = be_u16(blob, 0)
        rows = []
        for fid in range(n):
            o = 2 + fid*2
            if o + 2 > len(blob): break
            ptr = be_u16(blob, o)
            if ptr + 3 > len(blob): continue
            inner = be_u16(blob, ptr)
            n_e = blob[ptr+2]
            p = ptr + 3
            enemies = []
            for _ in range(n_e):
                if p + 7 > len(blob): break
                ex = be_u16(blob, p);   p += 2
                ey = be_u16(blob, p);   p += 2
                ez = be_u16(blob, p);   p += 2
                et = blob[p];           p += 1
                enemies.append((et, ex, ey, ez))
            rows.append(f"#{fid} inner={inner} {enemies}")
        return rows

    def _dump_collision(self, blob: bytes):
        if len(blob) < 4: return []
        first = be_u32(blob, 0)
        n = first // 4
        offs = []
        for i in range(n):
            if 4*i + 4 > len(blob): break
            offs.append(be_u32(blob, 4*i))
        rows = []
        for ti, o in enumerate(offs):
            if o + 1796 > len(blob): break
            block = blob[o:o+1796]
            for ti2 in range(256):
                row = block[4 + ti2*7:4 + ti2*7 + 7]
                rows.append(f"tileset{ti}\ttile{ti2}\t" +
                            " ".join(f"{b:02x}" for b in row))
        return rows

    def _extract_maps_mobile(self, outdir: Path) -> int:
        outdir.mkdir(parents=True, exist_ok=True)
        # Build resolvers (per-chapter)
        self._collect_mobile_tilesets()
        count = 0
        for slot, files in self.data.sp_slots.items():
            if not files: continue
            boot = files.get("boot_data.dat")
            mpk_index = (flat_pack_index(parse_mpk_index_mobile(boot))
                         if boot else {})
            # Group entries by pack: pack_idx -> list of (map_id, off, sz)
            by_pack = {}
            for mid, (pi, off, sz) in mpk_index.items():
                by_pack.setdefault(pi, []).append((mid, off, sz))
            mpks = sorted(n for n in files
                          if n.startswith("mpk") and n.endswith(".dat"))
            for mi, mpk_name in enumerate(mpks):
                blob = files[mpk_name]
                pack_entries = by_pack.get(mi)
                for entry in scan_mobile_mpk_chunks(blob, pack_entries):
                    parsed = entry["parsed"]
                    off    = entry["offset"]
                    map_id = entry.get("map_id")
                    img = self._render_mobile_map(parsed, slot_label=slot)
                    if img is None:
                        continue
                    # Sanitise both the map name (may contain Japanese
                    # newlines / path separators) and the slot label.
                    safe_name = self._safe_filename_part(parsed.get("name", ""))
                    safe_slot = self._safe_filename_part(
                        slot.replace(" ", "_"))
                    if map_id is not None:
                        fname = (f"{safe_slot}__"
                                 f"map{map_id:04d}__{safe_name}.png")
                    else:
                        fname = (f"{safe_slot}__{mpk_name}__"
                                 f"{off:08x}__{safe_name}.png")
                    img.save(outdir / fname)
                    count += 1
        return count

    def _collect_mobile_tilesets(self):
        """
        Build a per-chapter MobileTilesetResolver and stash on self.
        Returns a flat by_global dict (entry_id -> rendered RGBA Image)
        for legacy callers, but the renderer now uses the resolvers.
        """
        self._mob_resolvers = {}
        by_global = {}
        for slot, files in self.data.sp_slots.items():
            if not files:
                continue
            res = MobileTilesetResolver(files)
            self._mob_resolvers[slot] = res
            for eid, img in res.get_all_tilesets().items():
                if eid not in by_global:
                    by_global[eid] = img
        return by_global

    def _render_mobile_map(self, parsed, tile_imgs=None, slot_label=None,
                           resolver=None):
        """
        Render a mobile map. Tile encoding:
          bpt=3: 24-bit BE; layer0_id = v & 0xFFF; layer1_id = (v>>12) & 0xFFF
          bpt=2: BE u16; high byte = ts_sel, low byte = tile_num
          bpt=1: u8 = tile_num for the only loaded tileset
        Tilesets per chunk: ts0 (cpk entry_id) and ts1 (cpk entry_id), each
        with its own palette index. Selector 0 → ts0, selector 1 → ts1.

        Args:
            parsed: dict from parse_mobile_map_chunk
            tile_imgs: legacy entry_id->ICImage dict (used if no resolver)
            slot_label: chapter slot, used to look up resolver if not given
            resolver: MobileTilesetResolver for the chapter (preferred)
        """
        w, h = parsed["w"], parsed["h"]
        bpt = parsed["bpt"]
        td = parsed["tile_data"]
        if w <= 0 or h <= 0:
            return None

        ts0_id = parsed.get("ts0_id", 255)
        ts1_id = parsed.get("ts1_id", 255)
        pal0   = parsed.get("pal0", 0)
        pal1   = parsed.get("pal1", 0)

        # Resolve a resolver for the chapter
        if resolver is None:
            resolvers = getattr(self, "_mob_resolvers", None) or {}
            resolver = resolvers.get(slot_label)

        # Two tileset images
        ts_imgs = [None, None]
        if resolver is not None:
            if ts0_id != 255:
                ts_imgs[0] = resolver.get(ts0_id, pal0)
            if ts1_id != 255:
                ts_imgs[1] = resolver.get(ts1_id, pal1)
        else:
            # Legacy fallback: tile_imgs is entry_id -> ICImage
            if tile_imgs:
                if ts0_id != 255 and ts0_id in tile_imgs:
                    ts_imgs[0] = render_ic(tile_imgs[ts0_id])
                if ts1_id != 255 and ts1_id in tile_imgs:
                    ts_imgs[1] = render_ic(tile_imgs[ts1_id])

        TILE = 16
        canvas = Image.new("RGBA", (w * TILE, h * TILE), (0, 0, 0, 255))

        def place(t_id: int, px: int, py: int) -> None:
            ts_sel   = (t_id >> 8) & 0xF
            tile_num = t_id & 0xFF
            if 0 <= ts_sel < 2 and ts_imgs[ts_sel] is not None:
                ts = ts_imgs[ts_sel]
                tx = (tile_num % 16) * TILE
                ty = (tile_num // 16) * TILE
                if tx + TILE > ts.width or ty + TILE > ts.height:
                    return
                tile = ts.crop((tx, ty, tx + TILE, ty + TILE))
                canvas.paste(tile, (px, py), tile)

        n = w * h
        if bpt == 3:
            for y in range(h):
                for x in range(w):
                    p = (y * w + x) * 3
                    if p + 3 > len(td):
                        continue
                    v = (td[p] << 16) | (td[p+1] << 8) | td[p+2]
                    place(v & 0xFFF,         x * TILE, y * TILE)
                    place((v >> 12) & 0xFFF, x * TILE, y * TILE)
        elif bpt == 2:
            for y in range(h):
                for x in range(w):
                    p = (y * w + x) * 2
                    if p + 2 > len(td):
                        continue
                    v = (td[p] << 8) | td[p+1]
                    place(v, x * TILE, y * TILE)
        else:
            ts_sel = 0 if ts_imgs[0] is not None else 1
            for y in range(h):
                for x in range(w):
                    p = y * w + x
                    if p >= len(td):
                        continue
                    place((ts_sel << 8) | td[p], x * TILE, y * TILE)

        # Composite onto opaque black so saved PNGs aren't transparent
        out = Image.new("RGBA", canvas.size, (0, 0, 0, 255))
        out.alpha_composite(canvas)
        return out

    def _blit_tile(self, dest: Image.Image, cx, cy, ic: Optional[ICImage],
                   tile_num: int):
        if ic is None:
            return
        # 16×16 tile = lower-left 2×2 ic cells, but mobile tilesets store
        # each game tile as a 2×2 block of 8×8 cells. Map column count:
        ts_cols = ic.width // 16   # tiles wide
        if ts_cols == 0:
            return
        ttx = (tile_num %  ts_cols) * 16
        tty = (tile_num // ts_cols) * 16
        # Render the entire ic only once, then crop. To avoid re-rendering
        # repeatedly we cache.
        cache_key = id(ic)
        cache = getattr(self, "_ts_cache", None)
        if cache is None:
            cache = {}
            self._ts_cache = cache
        full = cache.get(cache_key)
        if full is None:
            full = render_ic(ic)
            cache[cache_key] = full
        if ttx + 16 > full.width or tty + 16 > full.height:
            return
        crop = full.crop((ttx, tty, ttx + 16, tty + 16))
        dest.alpha_composite(crop, (cx*16, cy*16))

    def _make_mobile_ts_cache_for_extract(self):
        """
        Build a (mc_id, variant) -> PIL Image callable backed by the loaded
        .sp mobile cpk tilesets. Same 4-tier fallback logic the MapTab's
        'Android, mobile tilesets' mode uses (exact → variant 0 → any
        variant → naive id-equals-id). Returns None for mc_ids with no
        mobile equivalent in any loaded chapter.
        """
        # Per-chapter MobileTilesetResolver lookup
        resolvers = {}
        for slot, files in self.data.sp_slots.items():
            if not files:
                continue
            try:
                resolvers[slot] = MobileTilesetResolver(files)
            except Exception:
                pass
        if not resolvers:
            return lambda mc, v=0: None

        # Slot label → JSON chapter stem map
        stem_to_slot = {}
        for slot in resolvers:
            path = self.data.sp_paths.get(slot)
            stem = Path(path).stem if path else slot.replace(" ", "")
            stem_to_slot[stem.lower()] = slot
            stem_to_slot[slot.replace(" ", "").lower()] = slot

        inv = self.data.cpk_to_mc_inverse()

        # Build "any variant of mc_id" lookup (lowest SAD wins)
        any_variant = {}
        for (mc, var), entries in inv.items():
            for chap, cpk_id, sad in entries:
                cur = any_variant.get(mc)
                if cur is None or sad < cur[3]:
                    any_variant[mc] = (chap, cpk_id, var, sad)

        def find_resolver(stem):
            slot = stem_to_slot.get(stem.lower())
            return resolvers.get(slot) if slot else None

        # Build-aware production (palette / cell_map / force-Android edits)
        # + normalize to 512px so map tiles are uniform 32px.
        from ..sprites.mobile_tile_to_android import (
            produce_build_tile, make_source_provider)
        try:
            builds_data = self.data.custom_palettes()
        except Exception:
            builds_data = {}
        prov = make_source_provider(self.data.sp_slots or {})
        obb = self.data.obb_files or {}

        img_cache = {}

        def get(mc_id, variant=0):
            key = (mc_id, variant)
            if key in img_cache:
                return img_cache[key]
            # Tier 1: exact
            for (chap, cpk_id, _sad) in inv.get(key, []):
                res = find_resolver(chap)
                if res is None: continue
                img = produce_build_tile(res, cpk_id, mc_id, variant,
                                         builds_data, obb=obb, normalize=True, source_provider=prov)
                if img is not None:
                    img_cache[key] = img; return img
            # Tier 2: (mc_id, 0)
            for (chap, cpk_id, _sad) in inv.get((mc_id, 0), []):
                res = find_resolver(chap)
                if res is None: continue
                img = produce_build_tile(res, cpk_id, mc_id, variant,
                                         builds_data, obb=obb, normalize=True, source_provider=prov)
                if img is not None:
                    img_cache[key] = img; return img
            # Tier 3: any variant of mc_id
            if mc_id in any_variant:
                chap, cpk_id, _var, _sad = any_variant[mc_id]
                res = find_resolver(chap)
                if res is not None:
                    img = produce_build_tile(res, cpk_id, mc_id, variant,
                                             builds_data, obb=obb,
                                             normalize=True, source_provider=prov)
                    if img is not None:
                        img_cache[key] = img; return img
            # Tier 4: naive id-equals-id rule, variant-aware
            for slot, res in resolvers.items():
                img = produce_build_tile(res, mc_id, mc_id, variant,
                                         builds_data, obb=obb, normalize=True, source_provider=prov)
                if img is not None:
                    img_cache[key] = img; return img
            img_cache[key] = None
            return None

        return get

    def _wrap_extract_with_magenta(self, base_cb):
        """Wrap a callable so None results render as a 512x512 magenta tile."""
        magenta = Image.new("RGBA", (512, 512), (255, 0, 255, 255))
        def get(mc_id, variant=0):
            img = base_cb(mc_id, variant)
            return img if img is not None else magenta
        return get

    def _extract_maps_android(self, outdir: Path,
                              mobile_tilesets: bool = False) -> int:
        """
        Render every Android map to PNG.

        Args:
            outdir: where to write the rendered PNGs
            mobile_tilesets: if True, render the maps using the loaded
                .sp MOBILE cpk tilesets via cpk_to_mc.json — useful as a
                "what would this map look like ported to mobile" preview.
                Tiles whose mc_id has no mobile equivalent get a magenta
                placeholder so they're clearly visible in the output.
                (Reuses the same MapTab fallback logic via _make_mobile_
                ts_cache and the magenta wrapper.)
        """
        outdir.mkdir(parents=True, exist_ok=True)
        if not self.data.obb_files:
            return 0

        # mc_overrides.json: per-map / per-(chunk18,chunk5) tileset assignments
        overrides = self.data.mc_overrides()

        png_cache = {}
        obb = self.data.obb_files

        def get_ts_obb(mc_id, variant=0):
            """Load mc{N}_{V}.png from the .obb (Android-native tilesets)."""
            key = (mc_id, variant)
            if key in png_cache:
                return png_cache[key]
            target = f"mc{mc_id}_{variant}.png"
            for k in obb:
                if Path(k).name == target:
                    try:
                        img = Image.open(
                            io.BytesIO(obb[k])).convert("RGBA")
                        png_cache[key] = img
                        return img
                    except Exception:
                        break
            png_cache[key] = None
            return None

        # Pick the tileset cache based on the requested mode.
        if mobile_tilesets:
            # Build a Mobile-cpk-backed tileset cache with magenta fallback
            # for any mc_id that has no mobile equivalent — same 4-tier
            # logic the MapTab's "Android, mobile tilesets" mode uses.
            base_cb = self._make_mobile_ts_cache_for_extract()
            get_ts = self._wrap_extract_with_magenta(base_cb)
        else:
            get_ts = get_ts_obb

        # Find mpkh*.dat and mpk*_*.dat in obb
        mpkh_keys = sorted(k for k in self.data.obb_files
                           if Path(k).name.startswith("mpkh"))
        count = 0
        for mpkh_key in mpkh_keys:
            mpkh_blob = self.data.obb_files[mpkh_key]
            packs = parse_mpkh_index(mpkh_blob)
            base_idx = "".join(c for c in Path(mpkh_key).stem
                               if c.isdigit())
            try:
                group = int(base_idx)
            except Exception:
                group = -1
            for pi, entries in enumerate(packs):
                pack_name = f"mpk{base_idx}_{pi}.dat"
                pk_key = next((k for k in self.data.obb_files
                               if Path(k).name == pack_name), None)
                if not pk_key:
                    continue
                pk = self.data.obb_files[pk_key]
                for (mid, off, sz) in entries:
                    if off + sz > len(pk):
                        continue
                    chunk = pk[off:off+sz]
                    parsed = parse_android_map_chunk(chunk)
                    if not parsed:
                        continue
                    # Resolve both slot tilesets. Engine parser is the source
                    # of truth; mc_overrides.json only overrides slot 0 when
                    # user_confirmed=True.
                    engine_info = parse_android_map_engine(chunk)
                    if engine_info is not None:
                        mc_id = engine_info["mc_id_slot0"]
                        variant = engine_info["variant_slot0"]
                        s1_id = engine_info["mc_id_slot1"]
                        s1_var = engine_info["variant_slot1"]
                    else:
                        mc_id = variant = s1_id = s1_var = None
                    # User-confirmed override wins for slot 0
                    ov_entry = overrides.get("by_map", {}).get(
                        map_key(group, pi, mid))
                    if ov_entry and ov_entry.get("user_confirmed"):
                        mc_id = ov_entry.get("mc_id", mc_id)
                        variant = ov_entry.get("variant", variant)
                    if mc_id is None:
                        # Final fallback: legacy by_group bucket
                        chunk18 = chunk[18] if len(chunk) > 18 else 0
                        chunk5 = chunk[5] if len(chunk) > 5 else 0
                        mc_id, variant, _src = lookup_primary_mc(
                            overrides, group, pi, mid, chunk18, chunk5,
                            default_mc_id=0, default_variant=0)
                    img = self._render_android_map(
                        parsed, get_ts,
                        primary_mc_id=mc_id, primary_variant=variant,
                        slot1_mc_id=s1_id, slot1_variant=s1_var)
                    if img is None:
                        continue
                    # Filename must encode the full (group, pack, map_id)
                    # tuple — same map_id appears in multiple mpkh groups,
                    # so a flat `map{mid}.png` would have ~16× the maps
                    # overwriting each other. Match the Map tab's listing
                    # format: `mpkh{g}_p{p}_map{m}.png`.
                    img.save(outdir /
                             f"mpkh{base_idx}_p{pi}_map{mid}.png")
                    count += 1
        return count

    def _render_android_map(self, parsed, ts_cache,
                            primary_mc_id=None, primary_variant=None,
                            slot1_mc_id=None, slot1_variant=None):
        """
        Render an Android map.

        Tile word (LE u16 per cell per layer):
          high_byte: SLOT SELECTOR. 0 = use slot-0 tileset, 1 = use slot-1
                     tileset. (Decoded 2026-05-13 from libjniproxy.so:
                     `LoadChipImage(slot, mc_id, variant)` is called twice
                     during map init, once for each slot, with mc_id+variant
                     read inline from the map header — see
                     `parse_android_map_engine`.)
          low_byte:  tile number (0-255) within the chosen tileset.

        Callers should resolve the two slots via `parse_android_map_engine`
        (or `mc_overrides.json` for user-confirmed overrides) and pass:
          - `primary_mc_id` / `primary_variant`  → slot 0
          - `slot1_mc_id`   / `slot1_variant`    → slot 1

        Either slot may be None (or mc_id = -1) to mean "no tileset for this
        slot — fall back to slot 0 for cells with that high_byte".

        ts_cache: callable (mc_id, variant) -> PIL Image  OR  dict {mc_id: Image}
        """
        w, h = parsed["w"], parsed["h"]

        if callable(ts_cache):
            def get_ts(mc_type, variant):
                return ts_cache(mc_type, variant)
        else:
            def get_ts(mc_type, variant):
                return ts_cache.get(mc_type)

        img_cache = {}  # (mc_id, variant) -> Image or None

        def get_cached(mc_id, variant):
            key = (mc_id, variant)
            if key not in img_cache:
                img_cache[key] = get_ts(mc_id, variant)
            return img_cache[key]

        # Normalise -1 (engine "no tileset for this slot") to None
        s0_id = primary_mc_id if (primary_mc_id is not None and primary_mc_id >= 0) else None
        s0_v  = primary_variant if primary_variant is not None else 0
        s1_id = slot1_mc_id   if (slot1_mc_id   is not None and slot1_mc_id   >= 0) else None
        s1_v  = slot1_variant if slot1_variant is not None else 0

        def resolve_cell(mc_type, cell_high_byte):
            """Pick the (mc_id, variant) for a cell. The parser stored the
            high_byte in the `variant` slot of the cell tuple; that high_byte
            is the slot selector. Dispatch to slot 0 or slot 1 accordingly,
            falling back to slot 0 when slot 1 is unset."""
            # If neither slot is configured, use the parser's raw values
            # (legacy behaviour — renders mc0_0 for everything).
            if s0_id is None and s1_id is None:
                return mc_type, cell_high_byte
            if cell_high_byte == 1 and s1_id is not None:
                return s1_id, s1_v
            # high_byte == 0 (or slot 1 unavailable): use slot 0
            if s0_id is not None:
                return s0_id, s0_v
            # slot 0 is None but slot 1 is set — borrow slot 1
            return s1_id, s1_v

        # Detect tile size (32px for 512×512, 16px for 256×256)
        TS = None
        for layer in parsed["layers"]:
            for cell in layer:
                mc_type, variant, _ = cell
                rmc, rv = resolve_cell(mc_type, variant)
                img = get_cached(rmc, rv)
                if img is not None:
                    TS = 32 if img.width >= 512 else 16
                    break
            if TS is not None:
                break
        if TS is None:
            TS = 32

        out = Image.new("RGBA", (w * TS, h * TS), (0, 0, 0, 255))

        for layer_idx, layer in enumerate(parsed["layers"]):
            for i, (mc_type, variant, tile_num) in enumerate(layer):
                # The engine skips any cell whose raw tile-word is 0x0000
                # (high_byte == 0 AND low_byte == 0). See DrawMapChips around
                # line 109856 in libjniproxy_c.c — the loop only stores a
                # slot id when `(uVar8 & 0xff) != 0 || uVar8 >> 8 != 0`.
                # This applies on every layer, base + overlays, since real
                # maps never store a legitimate tile-word of zero.
                if tile_num == 0 and variant == 0:
                    continue
                rmc, rv = resolve_cell(mc_type, variant)
                ts = get_cached(rmc, rv)
                if ts is None:
                    continue
                cx = (i % w) * TS
                cy = (i // w) * TS
                tcols = ts.width // TS
                if tcols == 0:
                    continue
                tx = (tile_num % tcols) * TS
                ty = (tile_num // tcols) * TS
                if tx + TS > ts.width or ty + TS > ts.height:
                    continue
                out.alpha_composite(ts.crop((tx, ty, tx + TS, ty + TS)), (cx, cy))
        return out
