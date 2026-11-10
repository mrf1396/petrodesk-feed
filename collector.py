#!/usr/bin/env python3
"""PetroDesk: respectful public-tag discovery; never bypasses access controls.

Only titles, links and discovery metadata are exported. This is not a full-text
scraper or an AI model, and 'first_seen' is not the publisher's publication time.
"""
from __future__ import annotations
import calendar
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / 'docs'
DOCS.mkdir(exist_ok=True)
TAGS = {
    'پتروشیمی': 'https://khabarfarsi.com/tags2/Eq4mnw==/%D9%BE%D8%AA%D8%B1%D9%88%D8%B4%DB%8C%D9%85%DB%8C',
    'صنعت پتروشیمی': 'https://khabarfarsi.com/tags2/GaojkQ==/%D8%B5%D9%86%D8%B9%D8%AA_%D9%BE%D8%AA%D8%B1%D9%88%D8%B4%DB%8C%D9%85%DB%8C',
    'شرکت پتروشیمی': 'https://khabarfarsi.com/tags2/F6og/%D8%B4%D8%B1%DA%A9%D8%AA_%D9%BE%D8%AA%D8%B1%D9%88%D8%B4%DB%8C%D9%85%DB%8C',
}
USER_AGENT = 'PetroDesk/0.8 (news discovery; no login or access bypass)'
TIMEOUT = 16
MAX_ITEMS = 500
REASONABLE_TITLE = re.compile(r'[^\s\W]',re.UNICODE)
ARTICLE = re.compile(r'^/u/(\d+)(?:/)?$',re.IGNORECASE)


def now_utc():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def canonical_link(link):
    """Allow only explicitly recognized public NewsIDs from khabarfarsi.com."""
    try:
        p = urlsplit(link)
        if p.scheme not in ('http','https') or p.hostname not in ('khabarfarsi.com','www.khabarfarsi.com'):
            return None
        m = ARTICLE.fullmatch(p.path)
        return f'https://khabarfarsi.com/u/{m.group(1)}' if m else None
    except ValueError:
        return None


def clean(s):
    return re.sub(r'\s+', ' ', html.unescape(str(s or ''))).strip()


def plausible(title):
    title = clean(title)
    if not (18 <= len(title) <= 240):
        return False
    if title in ('جدیدترین خبرها','پتروشیمی','صنعت پتروشیمی','شرکت پتروشیمی','صفحه اصلی'):
        return False
    return len(REASONABLE_TITLE.findall(title)) >= 8


def parse_cards(page_html, page_url, tag):
    soup = BeautifulSoup(page_html, 'html.parser')
    for x in soup(['script', 'style', 'nav', 'footer', 'form', 'noscript']):
        x.decompose()
    items = []
    seen = set()
    # Link to a canonical /u/<id> item is the strongest structural signal.
    # Avoid guessing news from general category links, menu items or images.
    for a in soup.find_all('a', href=True):
        link = canonical_link(urljoin(page_url, a['href']))
        if not link or link in seen:
            continue
        title = clean(a.get_text(' ', strip=True))
        if not plausible(title):
            heading = a.find_parent(['h1','h2','h3','h4'])
            if heading:
                title = clean(heading.get_text(' ',strip=True))
        if not plausible(title):
            continue
        seen.add(link)
        items.append({'id': hashlib.sha1(link.encode()).hexdigest()[:16],
                      'title': title, 'url': link,'discovery_source': 'خبر فارسی',
                      'tags': [tag], 'publisher_url':'', 'published_at': '',
                      'summary':'', 'first_seen':'', 'last_seen':''})
    return items


def robots_ok(session, target):
    p = urlsplit(target)
    uri = f'{p.scheme}://{p.netloc}/robots.txt'
    try:
        r = session.get(uri, timeout=TIMEOUT, allow_redirects=False)
        if r.status_code == 404:
            return (True, 'robots.txt absent (404)')
        if r.status_code != 200:
            return (False, f'robots.txt unavailable: HTTP {r.status_code}')
        parser = RobotFileParser()
        parser.parse(r.text.splitlines())
        return (parser.can_fetch(USER_AGENT, target), 'robots.txt parsed')
    except requests.RequestException as exc:
        return (False, f'robots.txt unreachable: {str(exc)[:120]}')


def get_tag(session, tag, url):
    allowed, reason = robots_ok(session, url)
    if not allowed:
        return [], {'tag':tag,'status':'unavailable/robots','count':0,'reason':reason,'url':url}
    try:
        response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        if urlsplit(response.url).hostname not in ('khabarfarsi.com','www.khabarfarsi.com'):
            return [], {'tag':tag,'status':'redirected-outside','count':0,'reason':'Redirect target is outside permitted news source', 'url':url}
        if response.status_code != 200:
            return [], {'tag':tag,'status':f'HTTP {response.status_code}','count':0,'reason':'No retry or access bypass', 'url':url}
        if 'html' not in response.headers.get('Content-Type','').lower():
            return [], {'tag':tag,'status':'wrong content-type','count':0,'reason':response.headers.get('Content-Type',''), 'url':url}
        result = parse_cards(response.text, url, tag)
        if not result:
            return [], {'tag':tag,'status':'parser-empty','count':0,'reason':'HTTP 200 but no recognizable news URL; do not claim coverage','url':url}
        return result, {'tag':tag,'status':'ok','count':len(result),'reason':'Extracted canonical /u/ news links','url':url}
    except requests.RequestException as exc:
        return [], {'tag':tag,'status':'network-error','count':0,'reason':str(exc)[:160],'url':url}


def read_old():
    path=DOCS/'items.json'
    try:
        obj=json.loads(path.read_text(encoding='utf-8'))
        return {x['url']:x for x in obj.get('items',[]) if canonical_link(x.get('url',''))}
    except (OSError,ValueError,TypeError,KeyError):
        return {}


def merge(old, result, stamp):
    for item in result:
        url=item['url']
        prev=old.get(url)
        if prev:
            prev['tags']=sorted(set(prev.get('tags',[])+item['tags']))
            prev['last_seen']=stamp
            if len(item['title']) > len(prev.get('title','')) and len(prev.get('title','')) < 20:
                prev['title']=item['title']
        else:
            item['first_seen']=stamp
            item['last_seen']=stamp
            old[url]=item
    result=sorted(old.values(),key=lambda x:x.get('first_seen',''),reverse=True)
    return result[:MAX_ITEMS]


def make_xml(items, stamp):
    from xml.etree import ElementTree as ET
    root=ET.Element('rss',version='2.0'); channel=ET.SubElement(root,'channel')
    ET.SubElement(channel,'title').text='PetroDesk | کشف خبر پتروشیمی از برچسب‌های خبر فارسی'
    ET.SubElement(channel,'link').text='https://khabarfarsi.com/'
    ET.SubElement(channel,'description').text='فقط عنوان و لینک؛ تاریخ first_seen زمان کشف است نه انتشار؛ متن کامل از ناشر دریافت شود.'
    ET.SubElement(channel,'language').text='fa'
    ET.SubElement(channel,'lastBuildDate').text=email.utils.format_datetime(dt.datetime.fromisoformat(stamp))
    for it in items[:100]:
        node=ET.SubElement(channel,'item')
        ET.SubElement(node,'title').text=it['title']
        ET.SubElement(node,'link').text=it['url']
        ET.SubElement(node,'guid',isPermaLink='true').text=it['url']
        ET.SubElement(node,'description').text='خبر کشف‌شده، منتشرکننده و متن کامل باید بررسی شوند. برچسب: '+', '.join(it.get('tags',[]))
        if it.get('first_seen'):
            try: ET.SubElement(node,'pubDate').text=email.utils.format_datetime(dt.datetime.fromisoformat(it['first_seen']))
            except (ValueError,TypeError): pass
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def write_json_atomic(path, obj):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)


def main():
    stamp=now_utc()
    session=requests.Session();session.headers.update({'User-Agent':USER_AGENT,'Accept':'text/html,application/xhtml+xml'})
    existing=read_old()
    statuses=[];discovered=[]
    for tag,url in TAGS.items():
        items,status=get_tag(session,tag,url)
        statuses.append(status)
        discovered.extend(items)
        print(f"{tag}: {status['status']} / {status['count']}")
        time.sleep(0.4)
    previously_known = set(existing)
    merged=merge(existing,discovered,stamp)
    # Preserve last known data even on blocking; never mark it as freshly discovered.
    write_json_atomic(DOCS/'items.json',{'schema':1,'generated_at':stamp,'status':'ok' if any(s['status']=='ok' for s in statuses) else 'no_live_access', 'sources':statuses, 'items':merged})
    write_json_atomic(DOCS/'coverage_status.json',{'checked_at':stamp,'sources':statuses, 'new_discoveries': len(set(x['url'] for x in discovered)-previously_known), 'total_archived':len(merged), 'notice':'A page failing access or parsing is unobserved, not empty. first_seen means discovery time.'})
    (DOCS/'feed.xml').write_bytes(make_xml(merged,stamp))
    print('Item count:',len(merged),'HTTP/parse successes:',sum(s['status']=='ok' for s in statuses))
    # This exit code keeps diagnostics accessible in GitHub Actions even if every page was blocked.
    return 0

if __name__=='__main__':
    sys.exit(main())
