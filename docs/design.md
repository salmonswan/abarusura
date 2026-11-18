# Design

The site for Abarusura RFC, a community rugby club in Hoima. Open `docs/design/prototype.html` in a browser to see and click the agreed design. The prototype is the reference. This file names the rules it follows.

Fixtures, scores and dates in the prototype are made up. The real ones come from Directus.

## Feel
- Heritage first. The club is named after the soldiers of Omukama Kabalega, and the site says so with pride.
- Alive. Pages move when you navigate, and the home page opens on moving photos. Motion never hides content.
- Matchday is one glance away. The next fixture and the last results sit right under the opening photo.

## Colours
| Name | Value | Use |
|---|---|---|
| navy | `#0C1432` | page background, text on light panels |
| navy2 | `#141f4a` | gradient end on page headers |
| line | `#1f2a55` | borders and dividers on navy |
| red | `#E62529` | buttons, kickers, the next-fixture panel, active tab line |
| mist | `#cfd3e6` | body text and nav links on navy |
| white | `#ffffff` | headings on navy, light panels |

Result pills: won `#e6f4ea` on `#1e6b35`, lost `#fde8e8` on `#a3171a`, upcoming `#eef0f6` on navy. Text and background pairs must meet WCAG 2.2 AA contrast.

## Type
- Headings, the club name, scores and values: Oswald 500 and 700, upper case, letter spacing 0.02em. Fallbacks: Impact, "Arial Narrow", sans-serif.
- Body: the system font stack.
- Kickers (the small line above a heading): red, 13px, bold, letter spacing 0.25em, upper case.

## The stripe
A 12px band of diagonal red and navy stripes, `repeating-linear-gradient(135deg, red 0 10px, navy 10px 20px)`. It sits under the header and stays still during page transitions.

## Layout
- **Header** on every page: the logo on a white disc, the club name, then Our story, Fixtures, Academy, Kabalega 7s, Partners, and a red "Join the club" button. The current page has a red underline.
- **Home:**
  1. The opening photo, full width, with a dark gradient from the left. Over it: the kicker "HOIMA · BUNYORO-KITARA · SINCE 2025", the heading "Kabalega's warriors play rugby", one line about the club, and two buttons: "Train with us" and "Our story".
  2. The matchday strip in three panels: the next fixture in red with a live countdown, then the last women's result and the last men's result on white.
  3. The stripe.
  4. The values band: Discipline, Integrity, Determination, Dedication, Diligence.
  5. Three story links: The name, The academy, Kabalega 7s.
  6. The footer: "Abarusura Rugby Football Club · A member of Uganda Rugby Union · Hoima".
- **Fixtures:** a page header with the season kicker, the stripe, the tabs All, Men, Women and Academy, then fixtures grouped by month. Each row has the date and time, the match or score, the team and home or away, and a pill (Upcoming, Won, Lost, Played).
- **Our story:** a scroll down a pitch. A ball moves from try line to try line as you scroll. Each step changes the picture beside it: 1890s the Abarusura, 2025 seven social workers, Today the academy (the 8 schools count up), Next the Kabalega 7s. It ends on "Run with the warriors" and a "Come to training" button.
- Every inner page uses the same header, stripe and footer.

## Motion
- **Page transitions** use view transitions. The old page fades left in 0.28s, the new one slides in from the right in 0.45s. The header and stripe stay put.
- **Opening photo:** the photos cross-fade every 6s with a slow zoom. Progress bars show the time on each photo.
- **Values band:** each value lights up in turn when the band scrolls into view.
- **Rules:**
  - Nothing is hidden until an animation runs. With scripts off or motion off, every word and picture is visible.
  - Anything that moves for more than 5 seconds has a Pause button. The choice is kept for the visit in sessionStorage under `abar-paused`.
  - With `prefers-reduced-motion: reduce`, there are no animations, transitions or view transitions. The opening shows the first photo only, with no Pause button.
  - The countdown still counts down with reduced motion on, because it is information and not decoration.

## Pictures
- The logo is in `frontend/static/images/logo.png`.
- No photos are in the repo yet. Many players are children, and the club has not yet confirmed consent for any photo. Photos go in `frontend/static/images/` once the club confirms consent for each one. Until then, `*.jpg` in that folder is git-ignored, so the prototype's photos only show on the owner's machine.
- Build the opening and the story steps so they work with no photo: the navy background and gradient stand in. The photo list should be easy to change in one place.
- Every picture needs alt text that says what it shows. The logo's alt text is the club name. Never name a child under a photo.

## States
Every part that reads from Directus (fixtures, results, partners) shows three states besides the data: loading, empty ("No fixtures yet"), and error (says the fixtures could not load and offers a retry). Never fall back to made-up data.
