# Defense Rulebook public-data team demo

Open index.html in Google Chrome, or visit https://getkres.github.io/ted-board/nfl/ after deployment. Choose an opponent, load the sample, change a supported input, inspect the counts and baseline, and download the selected team's PDF. Upload accepts one structured JSON play under 100 KB, using sample-play.json. Arbitrary playbook diagrams and PDFs require manual entry. Files are parsed only in the browser. No analytics, storage, form submission, or playbook service is used.

This is an October 22, 2026 snapshot, not a current data service. Source: FTN Data via nflverse and nflfastR/nflverse PBP. 11,441 eligible scrimmage plays, 7,011 dropbacks, and 32 teams. Last game October 19, 2026. There is no PFF, proprietary NGS tracking, BDB, film, or private club data in this publication.

## Method and limits

engine.js preserves the existing fixed policy. Minimum selected cell: 20 plays and three games; prior weight: 20 toward the same team's background. Exact and pooled sample counts are distinct. An unsupported personnel or formation input cannot change the forecast. Concept suggestions are football hypotheses, with no success-rate or optimal-play claim. Existing names containing pressure mean five-plus actual rushers, not a charted quarterback-pressure event.

Training: weeks 1-4. Original check: complete games in weeks 5-6. That check is development evidence, and changes to this UI do not create fresh predictive evidence. Grey output is mandatory unless the outcome's finite model Brier is strictly below its finite base-rate Brier, and support is adequate. Individual rule frequencies do not have a separately validated predictive edge. Intervals are Wilson 95% intervals for unpooled observed cell frequency, assume independent plays, and omit clustering and model uncertainty. They are not prediction-confidence intervals. The next-game estimator uses all available snapshot rows.

## License and provenance

This demo's code, data adaptations, predictions, and rulebooks: CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/. Attribution: FTN Data via nflverse, with nflfastR/nflverse play-by-play (CC BY 4.0). Adaptations: filtering, joins, outcome flags, pooled probability estimates, and summaries. Preserve attribution, change notices, source links, and the same license when distributing adaptations. The source is visible alongside the app, and downstream reuse is permitted under those terms.

https://github.com/nflverse#licensing
https://nflreadr.nflverse.com/reference/load_ftn_charting.html
https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html
https://github.com/nflverse/nflverse-data

A proprietary team version is a separate proposal using data the team and its vendors explicitly authorize for third-party processing, models, retention, and outputs. Team subscriptions do not automatically grant those rights. No working enterprise connector or security certification is claimed.

## Checks

node --test nfl/play.test.cjs

Existing engine checks remain in the local project at ~/biz/nfl/prototype/weekly/engine.test.js. The browser and PDF verification records for this delivery are retained in the job directory.
