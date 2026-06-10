# Format: Audio

*Audit 2026-06-10. Parsers: `ffd/music/parser.py`; bake: `_bake_audio` (0.7.23); engine: `Engine/src/audio/`.*

## Mobile + Android `snd.dat` (MFi container) — HIGH (fixed 0.4.0)

Uncompressed, all integers **BE**: 3 bank offsets (u32×3 at +0); per bank u16 count + (N+1) u32 relative offsets; blobs are self-contained **MFi** melodies (`melo` magic, `.mld`, MFi v5 per `vers 0500`/`supt MFi5PlugIn_DoCoMo`). Zero-length slots preserved (engine addresses by index). Bank roles from `class_1`: banks 0/1 → BGM channel, bank 2 → SFX channels. *History: the legacy parser scanned for gzip magic and found nothing — the container was never compressed (Incorrect, fixed).* **MFi `trac` event stream undecoded** → MFi→MIDI conversion deferred; `.mld` export is byte-exact.

## Android OGG banks — HIGH

OBB `mtxs`-wrapped OGGs (16-byte header strip) named `snd{bank}_{idx}`: bank 0 = BGM, bank 2 = SFX. `bgm_loop.dat` = per-BGM loop flags. `res.bin` carries the audio-name table (`parse_audio_names_resbin`). Map header supplies `field_bgm`/`battle_bgm` (the 7 u8s in LoadMapInfo). `ReserveSE` ids: 1 decide, 2 ok, 3 error.

## Baked form (FFSmith M8) — HIGH

ffmpeg transcodes OGG → **IMA-ADPCM WAV** (~2× OGG size vs ~9× PCM) as `audio/snd0_{id}.wav` / `snd2_{id}.wav`; `data/audio.bin` (`FAUD`) = loop-flag table. SDL2 decodes ADPCM WAV natively → no engine decoder dependency. **ffmpeg on PATH is a bake-time requirement** (audio skipped with warning otherwise).

## Open / hypotheses

- MFi trac stream (note events) — the blocker for MIDI.
- Title-screen BGM id: engine placeholder 18, unconfirmed by ear (LOW).
- Battle SFX mapping (per weapon/spell, data-driven) — undecoded; victory jingle (`ReserveJINGLE`) unimplemented.
- bank 1 on Android (Mobile uses banks 0/1 for BGM; Android `snd1_*` contents unexamined in docs — verify before assuming empty).
