# Search visibility

The published site now has static event-detail pages, populated state pages, event-type pages, and a complete chronological browse page. All expose real content and crawlable links without JavaScript. The homepage retains interactive filters and includes static event links and state navigation before JavaScript runs. The garage/account page remains `noindex` and is excluded from the sitemap.

Each upcoming occurrence gets a stable, source/date-based URL, its own title, description, canonical URL, Open Graph/Twitter preview, and Event JSON-LD matching visible facts. Dates without a confirmed structured time remain date-only. Unknown ticket prices, organizer identities, exact street addresses, availability, and generic scene images are not added to event schema. Rich-result eligibility or ranking is never guaranteed.

`robots.txt` allows crawling and advertises `https://usautomeets.com/sitemap.xml`. The XML sitemap lists the homepage and current public event/browse pages. Empty states remain in the all-state coverage page but do not receive thin indexable landing pages. Expired pages leave the sitemap and their generated files are removed; GitHub Pages serves a real 404 with navigation to upcoming listings. The legacy directory URL retains its homepage canonical/redirect.

The daily build refreshes the public moderation suppression list before publishing. If that check fails, publication stops. Confirmed-hidden imported events are excluded from generated pages, homepage data, and the sitemap on the next successful deployment. This is a static publication snapshot, not instant removal at the moment of a report. Reporting alone does not hide events. Member-submitted events currently appear through the community browser integration; this initial static search build covers the imported event dataset.

The IndexNow verification file and `search-config.json` are intentionally public ownership proof, not private credentials. After each deployment, the workflow notifies `api.indexnow.org` of current sitemap URLs. HTTP 200/202 means the notification was accepted, not that URLs are indexed. Google does not participate in this protocol; do not use the retired sitemap-ping URL or Google's limited-use Indexing API for ordinary event pages.

## Remaining owner-dashboard work

- Verify `usautomeets.com` in Google Search Console and Bing Webmaster Tools. Submit `https://usautomeets.com/sitemap.xml`, then inspect the homepage, an event page, and a state page. Verification codes must come from the owner's account; none have been fabricated or claimed submitted here.
- Review Cloudflare crawler settings and security logs. The site loads in a normal browser, while some automated fetches receive 403. This alone does not establish whether verified Google/Bing crawlers are blocked. Confirm their access through Search Console/Bing inspection and Cloudflare logs before changing rules. Avoid broadly disabling security protections.
- Check the actual live event markup with Google's Rich Results Test. Missing source facts can limit enhancements; obtain better organizer data rather than inventing required fields.
- Monitor indexing, impressions, duplicate/404 reports, and real user performance. Search engines choose when and whether to index and rank each page. There is no guaranteed placement across every search, social, or AI service.

References: [Google event markup](https://developers.google.com/search/docs/appearance/structured-data/event), [Bing IndexNow](https://www.bing.com/indexnow/getstarted), [Cloudflare managed robots.txt](https://developers.cloudflare.com/bots/additional-configurations/managed-robots-txt/).
