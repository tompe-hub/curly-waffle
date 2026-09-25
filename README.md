# curly-waffle

## Mandarin drill (`drill/`)

A ten-minute listening and speaking drill for the C1-by-June goal, built to run in the 05:40 desk block or on the train.

1. **Source.** Claude writes a 240–300 character passage in the register of the day's desk outlet (Monday Zaobao, Wednesday Caixin, Friday a Taiwan source in traditional characters) on one of six standing topics: cross-strait, South China Sea, export controls, China's economy, Singapore and ASEAN, chips and AI. Or paste the article you are reading, and the drill uses it verbatim. Claude cannot read the news from the page, so generated passages cover standing issues, not today's headlines.
2. **Listen.** The passage is read by the device's Mandarin voice at 0.85×, 1× or 1.2×, with the text hidden.
3. **Questions.** Four multiple-choice questions: gist, detail, inference, and one word in context.
4. **Retell.** About a minute, out loud. Browser speech recognition transcribes it where the browser allows; otherwise use keyboard dictation or type.
5. **Grade.** Claude scores coverage, accuracy, C1 range and grammar out of 5, estimates a CEFR level, and returns corrections, C1 upgrades and a model retelling to shadow.

Every run is logged as `{kind:'drill', key:'YYYY-MM-DD', runs:[…]}` under the viewer's private `data/users/<id>/d-<date>` documents. The streak counts consecutive days; weekends count when done and never break it. The week's key terms can be copied as tab-separated lines for Anki.

- `drill/drill.js` is the module. `MandarinDrill.mount({host, store, cloud})` renders into `host`, and `cloud` is the planner's `{ready, push}` adapter.
- `drill/index.html` is a standalone page with the same styling and adapter.

The drill runs inside the "The week, on one page" artifact, at the top of its Queue tab, published alongside it as `drill.js`. That artifact declares the `sample`, `db`, `user` and `downloads` capabilities.
