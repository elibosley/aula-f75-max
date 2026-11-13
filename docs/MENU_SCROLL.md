# Menu scrolling efficiency

Menu selection and wheel behavior are unchanged. The first detent still moves selection immediately. The existing spring follows the latest selection during rapid turns and reversals; reduced motion retains its existing behavior.

The renderer now skips menu tiles whose pixels cannot change. Highlight movement marks its old and new bounds and any text whose selected color changes. Row edits, headings, and footers mark their own bounds. Appearance changes still require a full redraw. Page changes and wake still invalidate the panel cache.

Within menu rows 24–111, the adapter keeps a 32-bit signature per scanline and sends only consecutive rows whose pixels changed. It reuses the Home tile-signature storage in a union. A row is not treated as valid until its tile finishes successfully. The adapter still yields after at most eight rendered rows. Panel byte handling, SPI clock, RGB interrupt guards, recovery, and radio code are unchanged. The cache adds 308 bytes of static storage, leaving 4,136 bytes of heap headroom in the first linked build. There is no full-screen framebuffer or sprite-cache increase.

The installed image `dae927fe…` measured about 13.54 completed frames per second during the existing five-second hardware display test. That is a baseline, not a result for this candidate.

In the same linked ARM diagnostic, the candidate rendered 2.73 tiles per frame rather than 15.92 and sent 1,806 display bytes per frame rather than 5,527. The linked test reconstructs the panel from its actual SPI commands and compares it with complete ARM-rendered frames. It covers menu/Home/submenu cache transitions, both themes, reduced motion, and rapid encoder reversals. An unchanged menu rendered zero tiles and sent zero display bytes. These are modeled results; physical speed and appearance require installation and observation.

The radio regression fixture waits for the wheel's debounced press and release, with at most 15 additional scheduler observations. Its former 20 ms raw press was exactly the production debounce threshold and passed only when slower drawing extended the sampled hold. Traces show a 20 ms sampled hold rejected on the candidate, a 21 ms hold accepted on the baseline, and the complete candidate radio test passing with a confirmed press. Each observation is independently bounded by the emulator. This checks acceptance rather than latency, because a scheduler observation can finish drawing or route work before returning. Production button timing and every route, pairing, and report assertion remain unchanged.
