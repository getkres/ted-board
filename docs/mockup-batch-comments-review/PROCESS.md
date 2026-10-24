# UI process notes

Reference: the existing Ted Board batch controls, pin conversation, and Archive controls from merged PR #42. These are original interface master copies, not claims of studying an unrelated artist.

Technique: value grouping and a shared left edge. Dark text and two-pixel structural edges sit on white paper; the brightest area is the textarea. The four-value light palette is white, #f2f2f2, #5d5d5d, and #111. Existing #e2402a is the small action accent. Edges are hard because they define controls. There is no simulated texture, lighting, or gradient. Archivo carries headings and body; Courier Prime carries dates.

Eight thumbnails were explored. Picks: #2 places the thread and composer below the existing controls, preserves one reading path, and works at 375 pixels; #5 has clear separation but crowds the phone with a side column; #7 gives the composer priority but pushes Ted's reply too far down. #2 is the final construction.

The notan keeps the composer distinct without competing with the mockup art. Rectangular construction uses 16-pixel insets, 16-pixel gaps, a shared left edge, and 44-pixel actions. Perspective and anatomy are not applicable to this flat interface. The construction drawing fixes the proportions before CSS.

Three color comps retain the current token system: the existing light palette is chosen, the existing dark palette remains supported, and an all-ink Send variant was rejected because the red action matches the board's established controls. The light is flat screen light, with no invented warm or cool material shading.

The clean drawing fixes the hierarchy of big, medium, and small forms before rendering. Final render and critique follow the implemented screenshots. This board contains synthetic data and is an offline review artifact, not a live upload.

Review revision: the batch dismissal label is now Sebastian's exact words, Not relevant anymore. It retains the same one-tap Archive action and five-second Undo. The composer is absent before the private capability is enabled. Its enabled layout, value structure, and compact viewer remain as studied. Updated final screenshots include the enabled and held-rollout states.
