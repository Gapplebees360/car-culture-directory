"""Build crawlable static pages from the same validated directory data."""
import hashlib
import html
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

BASE = 'https://usautomeets.com'
NAMES = dict(zip('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split(),
    ['Alabama','Alaska','Arizona','Arkansas','California','Colorado','Connecticut','Delaware','Florida','Georgia','Hawaii','Idaho','Illinois','Indiana','Iowa','Kansas','Kentucky','Louisiana','Maine','Maryland','Massachusetts','Michigan','Minnesota','Mississippi','Missouri','Montana','Nebraska','Nevada','New Hampshire','New Jersey','New Mexico','New York','North Carolina','North Dakota','Ohio','Oklahoma','Oregon','Pennsylvania','Rhode Island','South Carolina','South Dakota','Tennessee','Texas','Utah','Vermont','Virginia','Washington','West Virginia','Wisconsin','Wyoming']))
esc = lambda value:html.escape(str(value),quote=True)


def slug(value):
    return re.sub(r'[^a-z0-9]+','-',value.lower()).strip('-')


def event_path(event):
    identity = json.dumps([event.get('source'),event.get('source_id') or event['url'],event['date']],ensure_ascii=False,separators=(',',':'))
    return '/events/'+hashlib.sha256(identity.encode()).hexdigest()[:20]+'/'


def event_key(event):
    identity = json.dumps([event.get('source'),event.get('source_id') or event['url'],event['date']],ensure_ascii=False,separators=(',',':'))
    return 'imported:'+hashlib.sha256(identity.encode()).hexdigest()


def ld_json(data):
    return json.dumps(data,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')


def page(title,description,path,body,schema=None,image=None,image_alt=None):
    image = image or BASE+'/assets/hero-porsche.jpg'
    image_alt = image_alt or 'Representative car photography for USA Auto Meets'
    structured = '<script type="application/ld+json">'+ld_json(schema)+'</script>' if schema else ''
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} | USA Auto Meets</title><meta name="description" content="{esc(description)}">
<link rel="canonical" href="{BASE}{esc(path)}"><meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:type" content="website"><meta property="og:site_name" content="USA Auto Meets">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{BASE}{esc(path)}"><meta property="og:image" content="{esc(image)}"><meta property="og:image:alt" content="{esc(image_alt)}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{esc(title)}"><meta name="twitter:description" content="{esc(description)}"><meta name="twitter:image" content="{esc(image)}"><meta name="twitter:image:alt" content="{esc(image_alt)}">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/assets/site.css"><link rel="stylesheet" href="/assets/seo.css">{structured}</head>
<body class="seo-page"><a class="skip-link" href="#main">Skip to content</a><nav class="site-nav wrap" aria-label="Main navigation"><a class="brand" href="/">USA AUTO MEETS</a><div class="nav-links"><a href="/events/">All events</a><a href="/states/">Browse states</a><a href="/event-types/">Event types</a><a href="/community.html">Your garage</a></div></nav>
<main class="wrap seo-main" id="main">{body}</main><footer class="wrap"><a href="/">USA Auto Meets</a><p>Check the original organizer listing for changes, admission, cancellations, and entry requirements.</p></footer></body></html>'''


def summary(event):
    return f"{event['title']} in {event['city']}, {NAMES[event['state']]} on {event['date']}. Venue: {event['venue']}. See the schedule and original organizer listing."


def rows(events):
    return '<ul class="seo-list">'+''.join(f'''<li><article><p class="eyebrow">{esc(e['category'])} · <time datetime="{e['date']}">{e['date']}</time></p><h2><a href="{event_path(e)}">{esc(e['title'])}</a></h2><p>{esc(e['city'])}, {esc(NAMES[e['state']])} · {esc(e['venue'])}</p><p>{esc(e.get('time') or 'Check organizer for times')}</p></article></li>''' for e in events)+'</ul>'


def event_schema(event):
    data = {'@context':'https://schema.org','@type':'Event','name':event['title'],
            'url':BASE+event_path(event),'startDate':event['date'],
            'description':event.get('description') or summary(event),
            'eventAttendanceMode':'https://schema.org/OfflineEventAttendanceMode',
            'location':{'@type':'Place','name':event['venue'],'address':{'@type':'PostalAddress',
            'addressLocality':event['city'],'addressRegion':event['state'],'addressCountry':'US'}}}
    # A date-only value preserves an unknown time. Do not invent midnight, a timezone,
    # ticket price, availability, an organizer identity, or a street address.
    if event.get('end_date') and event['end_date']!=event['date']:
        data['endDate']=event['end_date']
    if event.get('image'):
        data['image']=[event['image']]
    return data


def homepage_content(document,events):
    cards=''.join(f'''<article class="event-card"><div class="event-card-body"><p class="eyebrow">{esc(e['category'])}</p><h3 class="event-title"><a href="{event_path(e)}">{esc(e['title'])}</a></h3><p><time datetime="{e['date']}">{e['date']}</time> · {esc(e['city'])}, {esc(e['state'])}</p><p>{esc(e['venue'])}</p><a class="event-link-btn" href="{event_path(e)}">EVENT DETAILS ↗</a></div></article>''' for e in events[:18])
    document=re.sub(r'<!-- SEO_GRID_START -->.*?<!-- SEO_GRID_END -->','<!-- SEO_GRID_START -->'+cards+'<!-- SEO_GRID_END -->',document,flags=re.S)
    links=' · '.join(f'<a href="/states/{slug(NAMES[s])}/">{esc(NAMES[s])}</a>' for s in sorted({e['state'] for e in events},key=lambda s:NAMES[s]))
    document=re.sub(r'<!-- SEO_STATES_START -->.*?<!-- SEO_STATES_END -->','<!-- SEO_STATES_START -->'+links+'<!-- SEO_STATES_END -->',document,flags=re.S)
    return document


def build_pages(root,events):
    pages={}
    def add(path,content):
        pages[path+'index.html']=content
    for event in events:
        name=NAMES[event['state']]
        path=event_path(event)
        source=esc(event['url'])
        image=(f'<figure><img class="seo-flyer" src="{esc(event["image"])}" alt="Source artwork for {esc(event["title"])}"><figcaption>Source artwork · {esc(event.get("source","Organizer listing"))}</figcaption></figure>' if event.get('image') else '')
        body=f'''<p class="seo-breadcrumb"><a href="/">Home</a> / <a href="/states/{slug(name)}/">{esc(name)} car events</a> / Event</p>
<p class="eyebrow">{esc(event['category'])}</p><h1>{esc(event['title'])}</h1><p class="seo-lede">{esc(event['city'])}, {esc(name)} · <time datetime="{event['date']}">{event['date']}</time>{' – '+esc(event['end_date']) if event.get('end_date') and event['end_date']!=event['date'] else ''}</p>
<dl class="seo-facts"><dt>Venue</dt><dd>{esc(event['venue'])}</dd><dt>Schedule</dt><dd>{esc(event.get('time') or 'Check organizer for times')}</dd><dt>Event type</dt><dd><a href="/event-types/{slug(event['category'])}/">{esc(event['category'])}</a></dd><dt>Source checked</dt><dd>{esc(event['verified_at'])} UTC</dd></dl>
<p>{esc(event.get('description') or summary(event))}</p>{image}<div class="hero-actions"><a class="button" href="{source}" rel="noopener noreferrer" target="_blank">ORGANIZER DETAILS / TICKETS ↗</a><a class="text-link" href="/community.html?event={event_key(event)}">Save / RSVP</a></div><p>USA Auto Meets is an event directory. Saving or RSVPing here does not reserve organizer admission. Follow the original source for tickets, eligibility, and current details.</p><p><a href="{source}" rel="noopener noreferrer" target="_blank">Original source: {esc(event.get('source','Organizer listing'))}</a> · <a href="/community.html">Report an event through Your Garage</a></p>'''
        add(path,page(f"{event['title']} — {event['city']}, {event['state']} — {event['date']}",summary(event),path,body,event_schema(event),event.get('image'),('Source artwork for '+event['title']) if event.get('image') else None))
    for state in sorted({e['state'] for e in events}):
        items=[e for e in events if e['state']==state]
        name=NAMES[state]; path='/states/'+slug(name)+'/'
        body=f'<p><a href="/states/">All states</a></p><h1>Car meets and car shows in {esc(name)}</h1><p class="seo-lede">{len(items)} upcoming listings with published dates. Browse cars and coffee, shows, meets, and motorsport events below.</p><p>Listings currently include events in {esc(", ".join(sorted({e["city"] for e in items})))}. Coverage varies; this is not a complete list of every event in {esc(name)}.</p>'+rows(items)
        add(path,page(f'{name} Car Meets, Car Shows & Cars and Coffee',f'Find upcoming car events in {name}: dates, venues, cars and coffee, meets, shows, and original organizer links.',path,body))
    states=''.join(f'<li><a href="/states/{slug(name)}/">{esc(name)} ({sum(e["state"]==code for e in events)})</a></li>' if any(e['state']==code for e in events) else f'<li>{esc(name)} — no verified upcoming listings yet</li>' for code,name in sorted(NAMES.items(),key=lambda item:item[1]))
    add('/states/',page('Browse Car Events by State','Browse US car meets, cars and coffee, auto shows, and track events by state. Check published dates and original sources.','/states/','<h1>Find car events by state</h1><p>All 50 states are in scope. States without confirmed listings remain visible here as coverage gaps.</p><ul class="seo-states">'+states+'</ul>'))
    categories=sorted({e['category'] for e in events})
    for category in categories:
        items=[e for e in events if e['category']==category]; path='/event-types/'+slug(category)+'/'
        add(path,page(f'{category} Events Across the USA',f'Find upcoming {category.lower()} events with dates, US locations, venue information, and original source links.',path,f'<p><a href="/event-types/">All event types</a></p><h1>{esc(category)} events across the USA</h1><p>{len(items)} upcoming dated listings. Select an event for venue and organizer details.</p>'+rows(items)))
    add('/event-types/',page('Browse Car Meets and Shows by Event Type','Explore cars and coffee, car shows, track days, autocross, cruise nights, and more upcoming automotive events.','/event-types/','<h1>Find your automotive scene</h1><ul>'+''.join(f'<li><a href="/event-types/{slug(c)}/">{esc(c)}</a></li>' for c in categories)+'</ul>'))
    add('/events/',page('Upcoming US Car Meets, Shows & Motorsport Events','Browse upcoming US automotive events by date, with venue details and original organizer listings.','/events/','<h1>Upcoming car meets, shows, and motorsport events</h1><p>Browse by <a href="/states/">state</a> or <a href="/event-types/">event type</a>. Dates and locations come from published sources; confirm details before travelling.</p>'+rows(events)))
    # Only remove this generator's known index files, never an arbitrary directory.
    manifest=root/'seo-manifest.json'
    previous=json.loads(manifest.read_text(encoding='utf8')) if manifest.exists() else []
    for old in previous:
        if old not in pages and re.fullmatch(r'/(?:events/[a-f0-9]{20}|states/[a-z-]+|event-types/[a-z-]+)/index\.html',old):
            target=(root/old.lstrip('/')).resolve()
            if target.is_relative_to(root.resolve()):
                target.unlink(missing_ok=True)
    for path,content in pages.items():
        target=root/path.lstrip('/'); target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(content,encoding='utf8')
    manifest.write_text(json.dumps(sorted(pages),indent=2)+'\n',encoding='utf8')
    namespace='http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('',namespace)
    sitemap=ET.Element('{'+namespace+'}urlset')
    for path in ['/']+[p.removesuffix('index.html') for p in sorted(pages)]:
        row=ET.SubElement(sitemap,'{'+namespace+'}url')
        ET.SubElement(row,'{'+namespace+'}loc').text=BASE+path
    # Omit lastmod rather than claiming an unchanged listing was modified at every scrape.
    ET.indent(sitemap)
    ET.ElementTree(sitemap).write(root/'sitemap.xml',encoding='utf-8',xml_declaration=True)
    print(f'SEO: {len(events)} event pages, {len(pages)} total browse/detail pages.')
