"""Bounded public website inspection. Never executes page code or publishes records.

``fetcher(url)`` may be injected in tests. It returns a mapping with ``status``,
``headers`` (case-insensitive names), ``body`` (UTF-8 text or bytes), and optional
``url`` (final URL). The production transport checks and pins public DNS for each
request/redirect; an injected fetcher is a trusted test boundary, not a proxy API.
"""
import datetime as dt
import difflib
import hashlib
import html
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
import unicodedata
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

try:
    from .update_events import STATES, validate_events
    from .import_facebook import STATE_NAMES
except ImportError:
    from update_events import STATES, validate_events
    from import_facebook import STATE_NAMES

USER_AGENT = 'USAAutoMeets/1.0 (+https://usautomeets.com/)'
MAX_BYTES = 1024 * 1024
MAX_PAGES = 3
MAX_NODES = 2000
MAX_ROBOTS_RULES = 1000
MAX_ROBOTS_PATTERN = 2048
EVENT_TYPES = {'Event', 'SportsEvent', 'Festival', 'ExhibitionEvent', 'SocialEvent'}
BUSINESS_TYPES = {'AutomotiveBusiness', 'AutoPartsStore', 'AutoRepair', 'AutoBodyShop', 'AutoDealer', 'AutoWash'}
CAR_PATTERN = re.compile(r'\b(?:car\s*(?:show|meet|cruise|rally)|cars?\s*(?:&|and)\s*coffee|caffeine\s*(?:&|and)\s*gasoline|cars?\s*(?:&|and)\s*caffeine|auto\s*show|automotive\s*(?:show|meet|event)|autocross|rallycross|track\s*day|drag\s*rac(?:e|ing)|dyno\s*day|hot\s*rod\s*(?:show|meet)|cruise[- ]?in|cruise\s*night)\b', re.I)
NEGATIVE_PATTERN = re.compile(r'\b(?:concert|birthday|wedding|flash\s*sale|job\s*fair|hiring\s*event|motorcycle[- ]only|bike\s*night|bike\s*show)\b', re.I)


class InspectionError(ValueError):
    """A bounded inspection failed closed; existing records must be retained."""


def public_url(value):
    if not isinstance(value, str) or len(value) > 2000 or re.search(r'[\x00-\x20\x7f\\]', value):
        raise InspectionError('Use a public HTTPS website URL without whitespace or control characters')
    try:
        parts = urlsplit(value)
        host = (parts.hostname or '').encode('idna').decode('ascii').lower()
        port = parts.port
    except (ValueError, UnicodeError) as error:
        raise InspectionError('Invalid website URL') from error
    if parts.scheme.lower() != 'https' or parts.username is not None or parts.password is not None or port not in (None, 443):
        raise InspectionError('Only credential-free HTTPS websites on port 443 are inspected')
    if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', host):
        raise InspectionError('A public DNS hostname is required; IP literals are not accepted')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal', '.home', '.lan', '.test', '.invalid', '.example', '.onion')):
        raise InspectionError('Private or reserved hostnames are not inspected')
    path = quote(parts.path or '/', safe="/%:@!$&'()*+,;=-._~")
    query = quote(parts.query, safe="%/?=&:@!$'()*+,;~-._")
    return urlunsplit(('https', host, path, query, ''))


def canonical_url(value):
    parts = urlsplit(public_url(value))
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in {'fbclid', 'gclid', 'msclkid'}]
    # Keep repeated/query parameter order: some servers use the first repeated
    # value. Tracking removal must not change which event the URL identifies.
    return urlunsplit(('https', parts.netloc, parts.path.rstrip('/') or '/', urlencode(query), ''))


def public_addresses(host, resolver=socket.getaddrinfo):
    addresses = []
    try:
        records = resolver(host, 443, type=socket.SOCK_STREAM)
    except OSError as error:
        raise InspectionError('Website DNS could not be resolved') from error
    for record in records:
        address = record[4][0]
        ip = ipaddress.ip_address(address)
        if not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_unspecified or ip.is_loopback or ip.is_link_local:
            raise InspectionError('Website DNS includes a non-public address')
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise InspectionError('Website DNS returned no usable public addresses')
    return addresses


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=10, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Do not resolve the hostname a second time. TLS still authenticates the
        # original hostname, and http.client emits that hostname in the Host field.
        raw = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def fetch_public(url):
    initial = urlsplit(public_url(url)).netloc
    for redirect in range(4):
        url = public_url(url)
        parts = urlsplit(url)
        if parts.netloc != initial:
            raise InspectionError('Cross-origin redirects require submitting the destination website separately')
        addresses = public_addresses(parts.hostname)
        connection = _PinnedHTTPS(parts.hostname, addresses[0])
        try:
            request_deadline = time.monotonic() + 10
            connection.request('GET', urlunsplit(('', '', parts.path or '/', parts.query, '')),
                               headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,application/ld+json,application/json,text/plain;q=0.8', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            headers = {k.lower(): v for k, v in response.getheaders()}
            if response.status in {301, 302, 303, 307, 308}:
                if redirect == 3 or not headers.get('location'):
                    raise InspectionError('Too many redirects or missing redirect destination')
                url = public_url(urljoin(url, headers['location']))
                continue
            if headers.get('content-encoding', 'identity').lower() not in {'', 'identity'}:
                raise InspectionError('Compressed responses are not accepted by the bounded inspector')
            if int(headers.get('content-length', '0') or 0) > MAX_BYTES:
                raise InspectionError('Website response exceeds the one-megabyte inspection limit')
            chunks, length = [], 0
            while True:
                remaining = request_deadline - time.monotonic()
                if remaining <= 0:
                    raise InspectionError('Website response exceeded the request time limit')
                if connection.sock is not None:
                    connection.sock.settimeout(min(10, remaining))
                chunk = response.read1(min(65536, MAX_BYTES + 1 - length))
                if not chunk:
                    break
                chunks.append(chunk)
                length += len(chunk)
                if length > MAX_BYTES:
                    raise InspectionError('Website response exceeds the one-megabyte inspection limit')
            body = b''.join(chunks)
            return {'status': response.status, 'headers': headers, 'body': body, 'url': url}
        except (OSError, http.client.HTTPException, ValueError) as error:
            if isinstance(error, InspectionError):
                raise
            raise InspectionError('Website request failed or exceeded its limit') from error
        finally:
            connection.close()
    raise InspectionError('Redirect limit exceeded')


def _robots_wildcard_match(pattern, path, terminal=False):
    """Match an anchored robots pattern without regex or backtracking.

    Stars separate literal segments. Earliest middle-segment matches leave the
    most room for later segments; an anchored final literal is reserved at the
    end before searching. Searches only advance through the request path.
    """
    segments = pattern.split('*')
    if len(segments) == 1:
        return path == pattern if terminal else path.startswith(pattern)
    first, last = segments[0], segments[-1]
    if not path.startswith(first):
        return False
    position = len(first)
    if terminal and last:
        if not path.endswith(last):
            return False
        limit = len(path) - len(last)
        middle = segments[1:-1]
    else:
        limit = len(path)
        middle = segments[1:]
    if position > limit:
        return False
    for segment in middle:
        if not segment:
            continue
        found = path.find(segment, position, limit)
        if found < 0:
            return False
        position = found + len(segment)
    return position <= limit


class Robots:
    """Conservative RFC 9309 wildcard/longest-match rules, plus crawl delay."""
    def __init__(self, body):
        groups = []
        agents, rules, delay, started = [], [], 0, False
        rule_count = 0
        for raw in body.splitlines():
            line = raw.split('#', 1)[0].strip()
            if ':' not in line:
                continue
            key, value = [s.strip() for s in line.split(':', 1)]
            key = key.lower()
            if key == 'user-agent':
                if started:
                    groups.append((agents, rules, delay))
                    agents, rules, delay, started = [], [], 0, False
                agents.append(value.lower())
            elif agents:
                started = True
                if key in {'allow', 'disallow'} and value:
                    rule_count += 1
                    if rule_count > MAX_ROBOTS_RULES:
                        raise InspectionError('Robots policy exceeds the inspection rule limit; inspection deferred')
                    if len(value) > MAX_ROBOTS_PATTERN:
                        raise InspectionError('Robots policy pattern exceeds the inspection length limit; inspection deferred')
                    rules.append((key == 'allow', value))
                elif key == 'crawl-delay':
                    try:
                        delay = max(delay, float(value))
                    except ValueError:
                        pass
        if agents:
            groups.append((agents, rules, delay))
        matches = [(max([len(a) if a != '*' else 0 for a in agents if a == '*' or a in 'usaautomeets'] or [-1]), rules, delay)
                   for agents, rules, delay in groups]
        best = max([item[0] for item in matches] or [-1])
        self.rules = [rule for rank, rules, _ in matches if rank == best for rule in rules] if best >= 0 else []
        self.delay = max([delay for rank, _, delay in matches if rank == best] or [0])

    def allowed(self, url):
        parts = urlsplit(url)
        def normalized(value):
            def decode(match):
                character = chr(int(match[1], 16))
                return character if re.fullmatch(r'[A-Za-z0-9._~-]', character) else '%' + match[1].upper()
            value = ''.join(''.join('%' + format(byte, '02X') for byte in character.encode('utf-8')) if ord(character)>127 else character for character in value)
            return re.sub(r'%([a-fA-F0-9]{2})', decode, value)
        path = normalized(parts.path + ('?' + parts.query if parts.query else ''))
        matches = []
        for allow, rule in self.rules:
            terminal = rule.endswith('$')
            raw = normalized(rule[:-1] if terminal else rule)
            if len(raw) > MAX_ROBOTS_PATTERN:
                raise InspectionError('Normalized robots pattern exceeds the inspection length limit; inspection deferred')
            if _robots_wildcard_match(raw, path, terminal):
                matches.append((len(raw.replace('*', '')), allow))
        return max(matches, default=(0, True))[1]


class Page(HTMLParser):
    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.structured, self.links, self.visible, self.title = [], [], [], []
        self.script, self.parts, self.hidden, self.in_title = False, [], 0, False
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script':
            self.hidden += 1
            self.script = attrs.get('type', '').split(';')[0].strip().lower() == 'application/ld+json'
            self.parts = []
        elif tag in {'style', 'noscript'}:
            self.hidden += 1
        elif tag == 'title':
            self.in_title = True
        if tag == 'a' and len(self.links) < 1000:
            self.links.append(attrs.get('href', ''))

    def handle_data(self, text):
        if self.script:
            self.parts.append(text)
        elif not self.hidden:
            self.visible.append(text)
            if self.in_title:
                self.title.append(text)

    def handle_endtag(self, tag):
        if tag == 'script':
            if self.script:
                try:
                    self.structured.append(json.loads(''.join(self.parts)))
                except (ValueError, RecursionError):
                    pass
            self.script = False
            self.parts = []
            self.hidden = max(0, self.hidden - 1)
        elif tag in {'style', 'noscript'}:
            self.hidden = max(0, self.hidden - 1)
        elif tag == 'title':
            self.in_title = False


def schema_nodes(values):
    stack = [(value, 0) for value in values]
    visited = 0
    while stack:
        value, depth = stack.pop()
        visited += 1
        if visited > MAX_NODES or depth > 24:
            raise InspectionError('Structured event data exceeds the inspection limit')
        if isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)
        elif isinstance(value, dict):
            yield value
            stack.extend((child, depth + 1) for child in value.values() if isinstance(child, (dict, list)))


def types(node):
    value = node.get('@type', [])
    values = value if isinstance(value, list) else [value]
    return {str(v).rsplit('/', 1)[-1] for v in values}


def text(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', str(value or '')))).strip()


def normalize(value):
    value = text(value).replace('&', ' and ')
    return re.sub(r'[^a-z0-9]+', ' ', unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()).strip()


def duplicate_reason(event, existing):
    for prior in existing:
        if prior.get('date') != event['date'] or prior.get('state') != event['state']:
            continue
        if normalize(prior.get('city')) != normalize(event['city']):
            continue
        a, b = normalize(prior.get('title')), normalize(event['title'])
        same_venue = normalize(prior.get('venue')) == normalize(event['venue'])
        similar_title = min(len(a), len(b)) >= 12 and re.findall(r'\d+', a) == re.findall(r'\d+', b) and difflib.SequenceMatcher(None, a, b).ratio() >= .94
        if same_venue and (a == b or similar_title):
            try:
                if canonical_url(prior.get('url', '')) == canonical_url(event['url']):
                    return 'Same original URL, compatible title, venue, city, and occurrence date'
            except InspectionError:
                pass
            return 'Same or very similar title at the same venue, city, and date'
    return ''


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?', value):
        raise ValueError('An explicit ISO calendar date including year is required')
    if 'T' in value:
        dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    return dt.date.fromisoformat(value[:10])


def convert_event(node, page_url, today):
    title = text(node.get('name'))
    description = text(node.get('description'))
    if len(title) < 5 or len(title) > 160 or not CAR_PATTERN.search(title) or NEGATIVE_PATTERN.search(title):
        raise ValueError('Event title does not establish a car-related event')
    status = str(node.get('eventStatus', '')).rsplit('/', 1)[-1]
    if status and status not in {'EventScheduled', 'EventRescheduled'}:
        raise ValueError('Cancelled, postponed, or unknown event status')
    mode = str(node.get('eventAttendanceMode', '')).rsplit('/', 1)[-1]
    if mode and mode != 'OfflineEventAttendanceMode':
        raise ValueError('Only an explicitly physical event is supported')
    if node.get('isAccessibleForFree') is not None and not isinstance(node['isAccessibleForFree'], bool):
        raise ValueError('Unexpected admission metadata')
    audience = node.get('audience')
    if isinstance(audience, dict) and re.search(r'private|invitation.?only|members.?only', text(audience.get('audienceType')), re.I):
        raise ValueError('Public attendance is not established')
    if re.search(r'\b(?:private event|invitation[- ]only|members[- ]only)\b', title + ' ' + description, re.I):
        raise ValueError('Public attendance is not established')
    start = _date(node.get('startDate'))
    end = _date(node.get('endDate') or node.get('startDate'))
    if end < start or end < today or start > today + dt.timedelta(days=366) or end > today + dt.timedelta(days=366):
        raise ValueError('Event is expired, reversed, or outside the one-year horizon')
    location = node.get('location')
    if not isinstance(location, dict) or 'VirtualLocation' in types(location):
        raise ValueError('A physical structured venue is required')
    address = location.get('address')
    if not isinstance(address, dict):
        raise ValueError('A structured US address is required')
    country = address.get('addressCountry')
    if isinstance(country, dict):
        country = country.get('name') or country.get('identifier')
    if str(country).upper() not in {'US', 'USA', 'UNITED STATES', 'UNITED STATES OF AMERICA'}:
        raise ValueError('US country must be explicit')
    state = text(address.get('addressRegion'))
    if state not in STATES:
        state = next((code for code, name in STATE_NAMES.items() if name.lower() == state.lower()), '')
    city, venue = text(address.get('addressLocality')), text(location.get('name'))
    if not state or not 2 <= len(city) <= 80 or not 3 <= len(venue) <= 200:
        raise ValueError('Complete US city, state, and named venue are required')
    url = canonical_url(urljoin(page_url, node.get('url') or page_url))
    if len(url) > 1000:
        raise ValueError('Original event URL exceeds the bounded import identity limit')
    if urlsplit(url).netloc != urlsplit(page_url).netloc:
        raise ValueError('Original event page must be on the inspected site')
    category = 'Car Show'
    for name, pattern in [('Cars & Coffee', r'coffee|caffeine'), ('Autocross', r'autocross'), ('Rallycross', r'rallycross'),
                          ('Track / Drag', r'track\s*day|drag\s*rac|dyno\s*day'), ('Cruise Night', r'cruise'), ('Road Rally', r'car\s*rally'), ('Pop-Up Meet', r'car\s*meet')]:
        if re.search(pattern, title, re.I):
            category = name
            break
    time_text = 'See original event page for times'
    if 'T' in node['startDate']:
        time_text = node['startDate'].split('T', 1)[1] + ' (as published by source)'
    identity = '|'.join(normalize(value) for value in [title, city, state, venue])
    source_id = url + '|' + hashlib.sha256(identity.encode('utf-8')).hexdigest()[:16]
    result = dict(title=title, date=start.isoformat(), end_date=end.isoformat(), city=city, state=state, venue=venue,
                  category=category, url=url, source='Website: ' + urlsplit(page_url).hostname, source_id=source_id,
                  verified_at=today.isoformat(), time=time_text,
                  description=(description[:1500] if description else 'Published on the original event page. Check the organizer for current details and admission.'))
    image = node.get('image')
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get('url') or image.get('contentUrl')
    if isinstance(image, str):
        try:
            image = public_url(urljoin(page_url, image))
            if len(image) <= 1000:
                result.update(image=image, image_kind='source_artwork', image_source=url)
        except InspectionError:
            pass
    return validate_events([result], today, verification_today=today)[0]


def inspect_website(url, existing_events=(), today=None, fetcher=None):
    """Inspect at most three same-origin HTML/JSON-LD pages, without publishing.

    Errors accessing robots or the initial page raise InspectionError. Rejected
    events and inaccessible discovered pages are reported; no date is invented.
    A positive ``automotive`` result is an evidence-based classification, not a
    guarantee that the operator or event is legitimate.
    """
    url = public_url(url)
    today = today or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=10)).date()
    fetcher = fetcher or fetch_public
    existing_events = list(existing_events)
    origin = 'https://' + urlsplit(url).netloc
    deadline = time.monotonic() + 60

    def read(target):
        if time.monotonic() > deadline:
            raise InspectionError('Inspection time budget exceeded')
        target = public_url(target)
        if 'https://' + urlsplit(target).netloc != origin:
            raise InspectionError('Discovery is limited to the submitted website origin')
        response = fetcher(target)
        final = public_url(response.get('url') or target)
        if 'https://' + urlsplit(final).netloc != origin:
            raise InspectionError('Cross-origin redirect is not inspected')
        body = response.get('body', '')
        if isinstance(body, bytes):
            if len(body) > MAX_BYTES:
                raise InspectionError('Website response exceeds the inspection limit')
            body = body.decode('utf-8', errors='replace')
        if not isinstance(body, str) or len(body.encode('utf-8')) > MAX_BYTES:
            raise InspectionError('Website response exceeds the inspection limit')
        return int(response['status']), {str(k).lower(): str(v) for k, v in response.get('headers', {}).items()}, body, final

    status, _, body, _ = read(origin + '/robots.txt')
    if status in {401, 403, 429} or status >= 500:
        raise InspectionError('Robots policy unavailable or access blocked; inspection deferred')
    robots = Robots(body if 200 <= status < 300 else '')
    if not robots.allowed(url):
        raise InspectionError('Website robots policy does not permit inspecting this page')
    if robots.delay > 5:
        raise InspectionError('Robots crawl delay exceeds the bounded inspector budget; manual source review needed')
    report = dict(url=url, final_url=url, site_host=urlsplit(url).hostname, automotive=False,
                  events=[], duplicates=[], rejected=[], pages_checked=0, notes=[])
    queue, visited = [url], set()
    while queue and report['pages_checked'] < MAX_PAGES:
        target = queue.pop(0)
        if target in visited or not robots.allowed(target):
            continue
        visited.add(target)
        if report['pages_checked']:
            time.sleep(max(.2, robots.delay))
        try:
            status, headers, body, final = read(target)
            if status != 200:
                raise InspectionError(f'Website returned HTTP {status}; no access-control bypass attempted')
            content_type = headers.get('content-type', '').split(';')[0].lower()
            if content_type not in {'text/html', 'application/xhtml+xml', 'application/ld+json', 'application/json'}:
                raise InspectionError('Only HTML or public structured event data is supported')
            if re.search(r'Pardon Our Interruption|Just a moment|verify you are human', body, re.I):
                raise InspectionError('Website access is blocked; no bypass attempted')
            report['pages_checked'] += 1
            if report['pages_checked'] == 1:
                report['final_url'] = final
            if content_type in {'application/ld+json', 'application/json'}:
                try:
                    values = [json.loads(body)]
                except (ValueError, RecursionError) as error:
                    raise InspectionError('Malformed structured event data') from error
                page = None
            else:
                page = Page(body)
                values = page.structured
            nodes = list(schema_nodes(values))
            if any(types(node) & BUSINESS_TYPES for node in nodes):
                report['automotive'] = True
            for node in nodes:
                if not types(node) & EVENT_TYPES:
                    continue
                try:
                    event = convert_event(node, final, today)
                    report['automotive'] = True
                    reason = duplicate_reason(event, existing_events + report['events'])
                    if reason:
                        report['duplicates'].append({'title': event['title'], 'date': event['date'], 'url': event['url'], 'reason': reason})
                    elif len(report['events']) >= 100:
                        report['rejected'].append({'title': event['title'], 'reason': 'Per-inspection 100-event limit reached; further dates deferred'})
                    else:
                        report['events'].append(event)
                except (ValueError, TypeError, KeyError, IndexError) as error:
                    report['rejected'].append({'title': text(node.get('name'))[:160], 'reason': str(error)})
            if page:
                # A business title plus explicit visible specialization is a lead,
                # never enough to classify an unrelated event as automotive.
                title = text(' '.join(page.title))
                visible = text(' '.join(page.visible))
                if re.search(r'\b(?:automotive|auto parts|car parts|performance tuning|car club|car detailing)\b', title, re.I) and re.search(r'\b(?:cars?|automotive|vehicles?|parts|tuning|detailing)\b', visible, re.I):
                    report['automotive'] = True
                visible_car_events = list(CAR_PATTERN.finditer(visible))
                if len(visible_car_events) >= 2 or (CAR_PATTERN.search(title) and visible_car_events):
                    # An ordinary HTML car calendar can join monitoring even when
                    # it needs a dedicated adapter. This never manufactures dates.
                    report['automotive'] = True
                for href in page.links:
                    if not re.search(r'event|calendar|car[-_ ]?show|cars[-_ ]?(?:and|&)[-_ ]?coffee|cruise', href, re.I):
                        continue
                    try:
                        candidate = public_url(urljoin(final, href))
                        if urlsplit(candidate).netloc == urlsplit(url).netloc and candidate not in queue and candidate not in visited and len(queue) < 12:
                            queue.append(candidate)
                    except InspectionError:
                        pass
        except (InspectionError, OSError) as error:
            if not report['pages_checked']:
                raise InspectionError(str(error)) from error
            report['notes'].append(f'{target}: {error}')
    if not report['events']:
        report['notes'].append('No new importable dated car events found. Unstructured, JavaScript-only, incomplete, and undated calendars require a source adapter; no recurring dates were generated.')
    return report
