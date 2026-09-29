# demo-shop

A small online shop that exists to be tested by
[Blue Mage](https://github.com/alvis051/bluemage), an AI agent that explores a
running web app and writes its Playwright end-to-end tests.

It plays the part of a customer's app: login, catalog, cart, coupons, a fake
checkout (success / declined / retryable) and order history, built with FastAPI
and server-rendered pages.

## No hand-written tests

There is no `tests/` directory, on purpose. Every test in this repo is written by
Blue Mage and arrives through a pull request from its bot; CI rejects any change to
`tests/` authored by anyone else.

Blue Mage measures those tests by how many seeded regressions they catch. The
regressions (the Bestiary) live outside this repo, so no generator can read them.
