# Journey: a visitor pauses the opening photos

User: anyone with a browser, no account

Steps:
1. Open the home page.
2. Press Pause under the opening photos.
3. Choose "Fixtures" in the header.
4. Choose "Abarusura RFC" in the header to go home.
5. Press Play.

Expect: After Pause the photos stop changing, the zoom and the progress bars stop, and the button reads Play. Back on the home page the first photo is paused, the bars are at the start and the button still reads Play. Play starts the photos again using the time left before pausing. The values light one by one when their band first enters view and stay lit after scrolling away and back.

Failure paths:
- Reduced motion on: there is no Pause button and no progress bars, only the first photo shows and all values are lit.
- Scripts off: there is no Pause button, nothing moves and all values are lit.
- New visit (new session): the photos play again.
- No photo files: the navy background stands in, the text is readable and Pause still works.
- Browser storage blocked: Pause and Play still work for the current page.

Covered by: frontend/e2e/pause.spec.ts, frontend/e2e/home.spec.ts
