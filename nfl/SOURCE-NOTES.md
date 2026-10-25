# Deck source notes, October 24, 2026

The team deck has exactly ten slides. This note accompanies the PDF decks. Slides are authored as PDF with editable JSON content and a ReportLab layout source, because the presentation artifact runtime is unavailable in this Mac session. No PowerPoint-native deliverable or PowerPoint QA is claimed.

## Team deck

1-6 and 8: local fixed snapshot ~/biz/nfl/prototype/weekly/snapshots/2026-10-22/, backtest.json, and dated rulebooks. Public sources: https://github.com/nflverse#licensing, https://nflreadr.nflverse.com/reference/load_ftn_charting.html, https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html, and https://github.com/nflverse/nflverse-data. The public app removes all historical BDB content and raw NGS material. FTN adaptations, demo code, predictions, and rulebooks are shared under https://creativecommons.org/licenses/by-sa/4.0/. PBP retains CC BY 4.0 attribution.

4: Rams five-plus-rush: model Brier 0.198512, baseline 0.195018, 63 held-out dropbacks, two games. 5: Rams seven-plus-box: model 0.237064, baseline 0.246470, 127 held-out scrimmage plays, two games. 6: third-and-long five-plus rush discovery 14/18, check 0/8. These are the old development holdout, with no new evidence from UI work.

7: https://www.pff.com/terms, introduction, supplemental terms, and sections 14.2-14.4; https://auth.sportsinfosolutions.com/Account/Register, terms 1-5; https://www.sportsinfosolutions.com/terms-of-service/; https://operations.nfl.com/game-operations-logistics/technology/performance-tracking-data-next-gen-stats; https://www.nfl.com/legal/terms/; and https://www.nfl.com/legal/subscriptions_terms. See DATA-RIGHTS.md for what is verified and what remains contract-specific.

8: BDB accepted access is Sebastian's explicit correction, corroborated by nine local CSV files. https://www.kaggle.com/competitions/nfl-big-data-bowl-2027/data. Competition data is not distributed in this package. 9-10: proposed pilot and product walkthrough, not measured time savings or a customer commitment.

