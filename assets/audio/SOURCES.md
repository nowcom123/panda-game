# Recorded firearm audio

The firing sounds below are recordings of actual firearms by **MrGungus**,
published on Freesound on December 9, 2024 under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).
The author describes recording a shooting session with a phone microphone and
identifies the pistol and shotgun on their respective source pages.

| Game asset | Bundled PCM master | Recording |
| --- | --- | --- |
| `gunshot.wav` (single/dual pistol, including overcharge) | `recordings/pistol.wav` | [gunshot 3, #773865](https://freesound.org/people/MrGungus/sounds/773865/) |
| `shotgun_blast.wav` (including overcharge) | `recordings/shotgun.wav` | [shotgun shoot, #773873](https://freesound.org/people/MrGungus/sounds/773873/) |

## Download provenance

Retrieved October 19, 2026 from the publicly available high-quality MP3 previews
linked by Freesound. These are encoded copies of the recordings, not the original
uploaded WAV files. No synthesized layers, pitch changes, or artificial reverb
were added.

- Pistol: https://cdn.freesound.org/previews/773/773865_15468302-hq.mp3
  - Download SHA-256: `dc1c2eb28e6cead28275932ccca8137b36154fe5cdeb41a8e10b5773038b4921`
- Shotgun: https://cdn.freesound.org/previews/773/773873_15468302-hq.mp3
  - Download SHA-256: `937c6bcf1adb224340c7f3a40e4a584756f1572b5cf32d191348a297254df1e1`

## Preparation and regeneration

Decoded with FFmpeg to mono, 44,100 Hz, signed 16-bit PCM. The decoded samples
were peak-normalized to 0.92 of the 16-bit positive full scale, with a linear
0.5 ms fade-in and 30 ms fade-out to prevent boundary clicks. The full decoded
duration and original playback speed are retained (approximately 0.680 s for
pistol and 1.203 s for shotgun).

The prepared PCM masters are bundled in `recordings/` so audio regeneration
requires neither network access nor an MP3 decoder. `make_gunshot()` and
`make_shotgun_blast()` in `generate_audio.py` copy these masters to the runtime
asset names. Do not replace these recordings with procedural synthesis.

## Mechanical actions (October 19, 2026 update)

The following are also CC0 recordings. Download URLs and SHA-256 hashes are
retained in `recordings/mechanics_sources.json`. Public HQ MP3 previews were
decoded to mono 44.1 kHz PCM, then edited into the bundled WAV masters.

| Runtime / master filename | Source recording |
| --- | --- |
| `shotgun_pump.wav` | [shotgun cock, MrGungus #773872](https://freesound.org/people/MrGungus/sounds/773872/) |
| `weapon_switch.wav`, `slide_release.wav` | [pistol cock 1, MrGungus #773869](https://freesound.org/people/MrGungus/sounds/773869/) |
| `reload.wav`, `dual_reload.wav` | [1911 Reload, nioczkus #396331](https://freesound.org/people/nioczkus/sounds/396331/), plus MrGungus #773869 |
| `empty_click.wav` | [Dry_Fire.wav, TampaJoey #588733](https://freesound.org/people/TampaJoey/sounds/588733/) — S&W 9mm field recording |
| `shotgun_reload.wav` | [Pump Action Shotgun Reload, AugustSandberg #508746](https://freesound.org/people/AugustSandberg/sounds/508746/), plus MrGungus #773872 |

Mechanical masters have a second-order 70 Hz high-pass filter to remove handling
rumble, short boundary fades, and peak normalization. No oscillators or generated
noise are used. The edits use these times in the decoded source audio:

- Pump: 0.00–0.44 s, unchanged pitch and duration.
- Switch: pistol cock 0.00–0.22 s. Slide release: 0.125–0.230 s.
- Empty click: 0.053–0.200 s, removing the leading delay.
- Pistol reload: 1911 reload 0.00–0.24 s at 0.10 s; 0.29–0.55 s at
  0.58 s; pistol cock 0.12–0.23 s at 0.99 s. Total: 1.25 s.
- Dual reload: two copies of that sequence, offset by 1.28 s. Total: 2.60 s.
- Shotgun reload: PA08 reload 2.50–3.70 s (after the initial dry fire) at
  0.08 s, followed by the pump recording at 1.29 s. Total: 1.75 s.

Mechanical playback levels are lower than discharge levels. Reload sequences
follow the game's reload duration, including speed perks. Firing clips always
play at their original pitch; independent voices preserve overlapping tails.
The pump starts 40 ms after firing so its recorded rear/forward impacts follow
the animation. A skipped frame still triggers exactly one pump and one ejection.

`make_shotgun_and_dual_sfx()` restores all these masters on regeneration.
CC0 does not require attribution; the source information is retained for
provenance and redistribution. Other audio files in this directory are outside
the scope of this source listing.

## Bullet time hum

`bullet_time_hum.wav` is synthesized by `make_bullet_time_sounds()` in
`generate_audio.py`: a seamless four-second harmonic hum. Playback glides
from 140 Hz to 58.8 Hz over 0.95 seconds, stays continuous during extensions,
and fades out over 0.30 seconds. It replaces the old entry/exit sweeps and
repeating clock/heartbeat pulse; no external recording is used for this effect.
