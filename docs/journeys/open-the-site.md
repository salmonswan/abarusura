# Journey: a visitor opens the site
User: anyone with a browser, no account
Steps:
1. Open the site.
Expect: The page loads with the title "Abarusura RFC". Directus, which will hold fixtures, results and sponsors, answers.
Failure paths:
- Directus is down: the smoke test fails, so a broken setup cannot pass the gates. The page itself does not read Directus yet.
Covered by: frontend/e2e/smoke.spec.ts
