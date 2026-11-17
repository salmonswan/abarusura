---
web_app: true
api: true
mobile_app: false
personal_data: true
eu_users: false
health_data: false
exchanges_health_records: false
card_payments: false
public_screens: true
---

# Project profile

What the app does: the public website of Abarusura RFC, a community rugby club in Hoima. It shows the club's story, fixtures and results, the academy, the Kabalega 7s tournament and partners. Club staff edit the content in a Directus admin.

What data it holds: public content (fixtures, results, news, partners, photos). Directus also holds the staff admin accounts. Photos may show children. A later join form may collect names and phone numbers.

Where its users are: mostly Hoima and the rest of Uganda, many on phones with slow or costly data.

Platforms: a static website for any browser, built with SvelteKit. Directus 12 with Postgres runs in Docker for the admin.

Run `devpipeline standards suggest` after changing the settings above.
