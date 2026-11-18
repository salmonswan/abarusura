# Journey: a visitor opens the site
User: anyone with a browser, no account
Steps:
1. Open the site.
2. Scroll to the foot of the home page.
Expect: The page loads with the title "Abarusura RFC". The header shows the club name, the links Our story, Fixtures, Academy, Kabalega 7s and Partners, and "Join the club". The opening shows the kicker, the heading "Kabalega's warriors play rugby", the line about the club and the buttons "Train with us" and "Our story". Below it come the stripe, the five values, the three story links and the footer. Directus, which will hold fixtures, results and sponsors, answers.
Failure paths:
- Scripts off: every word, the first photo, the values and the links are visible.
- No photo files: the navy background and gradient stand in, and the first photo's alt text is still read out.
- Directus is down: the smoke test fails, so a broken setup cannot pass the gates. The page itself does not read Directus yet.
Covered by: frontend/e2e/smoke.spec.ts, frontend/e2e/home.spec.ts
