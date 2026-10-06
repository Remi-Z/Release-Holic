# Source and library notes

| Source | Implementation | Interpretation / limits |
| --- | --- | --- |
| TMDB | Narrow HTTPX clients for movie/TV identities, videos, movie regional dates, and watch providers | Operator read token required. Availability is a first-observed country/platform fact; provider data is attributed to JustWatch. TMDB metadata needs attribution and a commercial agreement for commercial use. |
| TVmaze | Show search/details and episode schedule client | Source season/special numbering is retained. Date-only air dates have no invented time. Attribute TVmaze and comply with CC BY-SA. |
| Bangumi | Subject/episode pagination and relationship candidates | Only explicitly identified source relationships resolve into known catalogue works. Other relation labels remain metadata; source terms need checking for the deployment. |
| Kakuyomu | Dedicated Parsel metadata/index parser, pagination, optional Playwright rendering | Complete chapter count required. No bodies. Schedules are expectations. Stored HTML fixtures are illustrative and need comparison with live layouts. |
| KADOKAWA | Separate release/search-list and product parser | JSON-LD and semantic release fields, product IDs, ISBNs, edition format/language, exact volume wording. Live selectors still need validation. |
| Gagaga / Shogakukan | Release-list parser, ISBN-derived Shogakukan product key, product parser | Uses the eight-digit product key from a Japanese ISBN. Missing listing ISBNs remain unresolved; no guessed year. |
| NDL Search | SRU title/author search and identifier resolution | Underlying records can have different reuse conditions. Identifier-resolution behavior still needs live validation. |
| openBD | ISBN metadata enrichment | Optional enrichment failure does not discard valid publisher metadata. Compact publication dates retain day/month precision. |
| Apple / Netflix / Disney | Official press-page monitors assigned to a work | Match titles/aliases and enqueue review proposals. Page layouts and robots/collection behavior need live validation. |
| RSS / Atom / YouTube | feedparser, title/alias matching for channel feeds, content extraction | Sources stay scoped to a selected story; suggestions require review. Additional domains require operator configuration. |
| User article URLs | Scrapy + Trafilatura | Bounded article text, evidence references, and optional model extraction. No broad search crawler or X scraping is enabled by default. |

Official source documentation: [TMDB](https://developer.themoviedb.org/docs/faq), [TVmaze](https://www.tvmaze.com/api), [Bangumi](https://github.com/bangumi/api), [Kakuyomu schedules](https://kakuyomu.jp/help/entry/scheduled_episode), [Gagaga releases](https://gagagabunko.jp/release/index.html), [NDL API](https://ndlsearch.ndl.go.jp/en/help/api), [openBD](https://openbd.jp/). [AniList's terms](https://docs.anilist.co/guide/terms-of-use) restrict competing tracking services, so it is excluded.

The selected code libraries use permissive licences: Quasar/Vue/TanStack Virtual/Django Ninja/Pydantic/PydanticAI are MIT; Django/Celery/Scrapy/Parsel/HTTPX are BSD variants; feedparser is BSD-2-Clause; modern Trafilatura is Apache-2.0. PostgreSQL uses the PostgreSQL License; RabbitMQ is MPL-2.0. Their distribution notices and transitive dependencies still belong in release packaging. These code licences do not grant source-data reuse rights.

Version ranges are in each application's manifest. Registry connectivity prevented resolving/verifying lockfiles in the implementation environment; pin the successful dependency resolution after build and acceptance validation.
