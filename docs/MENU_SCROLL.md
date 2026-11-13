# Menu scrolling efficiency

Menu selection and wheel behavior are unchanged. The first detent still moves selection immediately. The existing spring follows the latest selection during rapid turns and reversals; reduced motion retains its existing behavior.

The renderer now skips menu tiles whose pixels cannot change. Highlight movement marks its old and new bounds and any text whose selected color changes. Row edits, headings, and footers mark their own bounds. Appearance changes still require a full redraw. Page changes and wake still invalidate the panel cache.

Within menu rows 24–111, the adapter keeps a 32-bit signature per scanline and sends only consecutive rows whose pixels changed. It reuses the Home tile-signature storage in a union. A row is not treated as valid until its tile finishes successfully. The adapter still yields after at most eight rendered rows. Panel byte handling, SPI clock, RGB interrupt guards, recovery, and radio code are unchanged. The cache adds 308 bytes of static storage, leaving 4,136 bytes of heap headroom in the first linked build. There is no full-screen framebuffer or sprite-cache increase.

The installed image `dae927fe…` measured about 13.54 completed frames per second during the existing five-second hardware display test. That is a baseline, not a result for this candidate.

In the same linked ARM diagnostic, the candidate rendered 2.73 tiles per frame rather than 15.92 and sent 1,806 display bytes per frame rather than 5,527. The linked test reconstructs the panel from its actual SPI commands and compares it with complete ARM-rendered frames. It covers menu/Home/submenu cache transitions, both themes, reduced motion, and rapid encoder reversals. An unchanged menu rendered zero tiles and sent zero display bytes. These are modeled results; physical speed and appearance require installation and observation.
