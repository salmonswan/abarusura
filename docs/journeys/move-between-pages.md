# Journey: a visitor moves between pages
User: anyone with a browser, no account
Steps:
1. Open the home page.
2. Choose "Our story" in the header.
3. Choose "Abarusura RFC" in the header to go home.
Expect: The Our story page shows its page header, the stripe and the footer. The header stays in place. The "Our story" link is underlined and marked as the current page. Focus and scroll start at the top of the new page. Back home, no header link is marked current.
Failure paths:
- Keyboard only: the first Tab stop is "Skip to content", and it moves focus to the page content.
Covered by: frontend/e2e/navigate.spec.ts
