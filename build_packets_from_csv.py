#!/usr/bin/env python3
"""Build packets.json + upcoming.json from published Sheet CSVs (Intel + Queue A:B).
Usage: build_packets_from_csv.py <intel.csv> <queue.csv> <packets.json> <upcoming.json>
Mirrors the dashboard's radiusTier and the v9.6 _packetId (md5) exactly, so the
output matches the sample packets.json generated from the live Intel tab.
The Queue CSV supplies display names (who); handles missing from it fall back
to a prettified handle, mirroring the dashboard's _who().
"""
import csv, hashlib, json, math, os, re, sys
from datetime import date, datetime, timezone

def has_phrase(hay, phrase):
    h = ' ' + re.sub(r'[^a-z0-9]+', ' ', str(hay or '').lower()) + ' '
    return (' ' + phrase + ' ') in h

def haversine_mi(lat1, lon1, lat2, lon2):
    R = 3958.8
    dlat = math.radians(lat2 - lat1); dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def radius_tier(p):
    towns, unis, loc = p['towns'], p['unis'], p['location']
    hay = towns + ' ' + unis + ' ' + loc
    if has_phrase(hay, 'potsdam') or has_phrase(unis, 'clarkson') or has_phrase(unis, 'suny potsdam'):
        return 0
    if has_phrase(unis, 'slu') or has_phrase(unis, 'st lawrence') or has_phrase(unis, 'suny canton'):
        return 1
    for t in ['canton', 'norwood', 'norfolk', 'madrid']:
        if has_phrase(hay, t): return 1
    for t in ['massena', 'ogdensburg', 'gouverneur', 'colton', 'pierrepont', 'parishville', 'hermon', 'st lawrence county']:
        if has_phrase(hay, t): return 2
    for t in ['watertown', 'malone', 'lowville', 'lake placid', 'saranac lake', 'tupper lake', 'alexandria bay', 'clayton', 'jefferson county', 'franklin county', 'lewis county', 'essex county', 'north country']:
        if has_phrase(hay, t): return 3
    if [x for x in towns.split(',') if x.strip()]: return 3
    if p['lat'] is not None and p['lng'] is not None:
        d = haversine_mi(44.67, -74.98, p['lat'], p['lng'])
        if d <= 15: return 0
        if d <= 30: return 1
        if d <= 60: return 2
        if d <= 110: return 3
    return 4

def who(handle, who_by):
    w = who_by.get(handle.strip().lower(), '')
    if w: return w
    s = re.sub(r'[@_]+', ' ', handle or '').strip()
    return re.sub(r'\b\w', lambda m: m.group(0).upper(), s) or 'Unknown source'

def fnum(v):
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None

intel_csv, queue_csv, packets_out, upcoming_out = sys.argv[1:5]

def _check_header(path, required, name):
    with open(path, newline='', encoding='utf-8') as f:
        header = next(csv.reader(f), [])
    missing = [c for c in required if c not in header]
    if missing:
        sys.exit(name + ' CSV missing columns: ' + ', '.join(missing))

_check_header(queue_csv, ['handle', 'display_name'], 'Queue')
_check_header(intel_csv, ['date', 'handle', 'headline', 'briefing', 'location', 'topic', 'event_date', 'source', 'lat', 'lng', 'stype', 'unis', 'towns'], 'Intel')
who_by = {}
with open(queue_csv, newline='', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        h = (r.get('handle') or '').strip().lower()
        if h and h not in who_by:
            who_by[h] = r.get('display_name') or ''
packets = []
with open(intel_csv, newline='', encoding='utf-8') as f:
    for r in csv.DictReader(f):
        p = {
            'date': str(r.get('date') or '')[:10],
            'handle': str(r.get('handle') or ''),
            'headline': str(r.get('headline') or ''),
            'briefing': str(r.get('briefing') or ''),
            'location': str(r.get('location') or '')[:120],
            'topic': (str(r.get('topic') or 'other')).lower(),
            'eventDate': str(r.get('event_date') or '')[:10],
            'source': str(r.get('source') or '')[:160],
            'lat': fnum(r.get('lat')),
            'lng': fnum(r.get('lng')),
            'stype': (str(r.get('stype') or 'instagram').lower() if str(r.get('stype') or '').lower() in ('instagram', 'facebook', 'web') else 'instagram'),
            'unis': str(r.get('unis') or ''),
            'towns': str(r.get('towns') or ''),
        }
        p['who'] = who(p['handle'], who_by)
        p['ring'] = radius_tier(p)
        p['id'] = 'p-' + hashlib.md5((p['handle'] + '|' + p['date'] + '|' + p['headline']).encode()).hexdigest()[:12]
        packets.append(p)
packets.sort(key=lambda p: p['date'], reverse=True)
today = date.today().isoformat()
upcoming = [p for p in packets if p['topic'] in ('event', 'deadline') and re.match(r'^\d{4}-\d{2}-\d{2}$', p['eventDate']) and p['eventDate'] >= today]
upcoming.sort(key=lambda p: p['eventDate'])
rings = [0, 0, 0, 0, 0]
for p in packets: rings[p['ring']] += 1
meta = {'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'source': '315Signal2 Intel tab (published CSV)', 'version': 'v9.5',
        'total': len(packets), 'byRing': rings,
        'dated': sum(1 for p in packets if re.match(r'^\d{4}-\d{2}-\d{2}$', p['eventDate']))}
for _data, _out in (({'meta': meta, 'packets': packets}, packets_out), ({'meta': meta, 'upcoming': upcoming}, upcoming_out)):
    _tmp = _out + '.tmp'
    with open(_tmp, 'w') as _f:
        json.dump(_data, _f)
    os.replace(_tmp, _out)
print('packets:', len(packets), 'rings:', rings, 'upcoming:', len(upcoming))
