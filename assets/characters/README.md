# Desk companions

Mochi is a keyboard dog, Pip is a small robot, and Ren is an anime guy. The downloadable set also includes Lumi, the original lavender-haired companion. The three new atlases were created with the built-in image-generation tool. Their exact prompts are in `generation-prompts.json`.

Each character has twelve poses. The six base poses are idle, blink, type-left, type-right, cheer, and sleep. Six bonus poses make three paired scenes: a drink break, a stretch, and a headphone groove. Normal typing alternates the hands every 180 ms. Flow uses 120 ms and Zoom uses 85 ms, matching the existing firmware animation timing.

The animation-efficiency candidate also includes a visiting calico cat with sixteen walk, blink and wave frames. It visits all four companions, respects reduced motion and stays behind notification signs. The generated source and exact built-in image-generation prompt are in `visiting-cat/`; `scripts/build_visitor_assets.py` produces the native 20×20 atlas and bounded run-length data. See [animation and transfer efficiency](../../docs/ANIMATION_AND_TRANSFER.md) for build and verification boundaries.

Living desk mode chooses short idle scenes with a 12–28 second cooldown between scenes and a 5–11 second delay after typing and no immediate repeats. The characters have independent random sequences. Typing in the demo field interrupts a scene immediately. A typing streak can trigger a short celebration after typing stops. Reduced motion holds the idle pose. Demo text and timing remain in the page and are not sent to the keyboard or server.

Build the packs from the repository root:

```sh
.venv/bin/python scripts/build_character_packs.py
```

The output is in `ui/assets/characters/`. Each character includes twelve PNG frames, a twelve-frame 80×80 RGB565 file, a manifest, and a ZIP with checksums and both original atlases. The compatible `pet_assets.h` contains only the six base poses. RGB565 uses little-endian words. Color zero is transparent, and opaque black uses color one. Previews show the same quantized colors and transparency as the native data.

The firmware bank uses 64 palette entries per character and bounded LZ decoding into a 4800-byte cache. Decoding advances only through the current display tile so key scanning and USB reports run between slices, including the first key after idle. Token reads extract covered bytes rather than walking individual bits. Wake tests separately check short key reports, wheel recognition, and completion of all sixteen fresh display tiles before the backlight turns on. `scripts/build_companion_bank.py` generates the bank from all twelve native-size poses. It does not access USB or external storage. The gallery’s firmware previews use the same palette colors.

The gallery is served at `/companions.html` by the existing Studio server. It previews artwork without reading or writing keyboard settings. `ui/companion-motion.js` owns the new preview behavior, and `scripts/test_companion_motion.cjs` tests its sequencing and interruption rules.

The firmware source integrates all four characters and the bonus scenes. Installing a different compiled bank requires a firmware rebuild, the normal validation checks and guarded installation. Menu > Screen selects a pet, appearance and motion preference. Settings records before version 6 keep Lumi by default. Linked builds still need validation and guarded installation before hardware acceptance. The pack ZIP is not a flashable image. Selection through the Screen menu is implemented in the candidate. Uploading additional sprites without a firmware rebuild is not implemented. The generated packs have not been installed or physically tested on the keyboard.

The default asset compiler still produces the original files byte for byte. A separate pack can also be compiled without replacing those files:

```sh
.venv/bin/python scripts/build_pet_assets.py \
  --source assets/characters/keyboard-dog/source-atlas.png \
  --output analysis/keyboard-dog-pack
```
