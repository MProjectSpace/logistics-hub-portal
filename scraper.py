#!/usr/bin/env python3
import argparse, json, logging, os, re, sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SOURCE_URL='https://ibstpks.pelindo.co.id/webaccess/'
PORTAL_URL='https://mprojectspace.github.io/logistics-hub-portal/'
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')

def clean(s): return re.sub(r'\s+',' ',s or '').strip()

def title_parts(s):
    m=re.match(r'^(.*?)\s*\(([^()]*)\)\s*$',clean(s))
    return (clean(m.group(1)),clean(m.group(2))) if m else (clean(s),'-')

def blocks(container):
    if not container: return []
    parts=re.split(r'<hr\b[^>]*\bclass\s*=\s*["\'][^"\']*\bves_along_sched_hr\b[^"\']*["\'][^>]*>',str(container),flags=re.I)
    return [BeautifulSoup(p,'html.parser') for p in parts if 'ves_along_sched' in p]

def parse_block(block, history=False):
    divs=block.select('div.ves_along_sched')
    if not divs: return {}
    title=''
    for b in block.find_all('b'):
        if clean(b.get_text(' ',strip=True)):
            title=clean(b.get_text(' ',strip=True)); break
    if not title: return {}
    name,code=title_parts(title)
    item={'vesselName':name,'vesselCode':code,'voyage':'-'}
    lines=[]
    for d in divs:
        if d.find('a',attrs={'data-url':True}): continue
        t=clean(d.get_text(' ',strip=True))
        if t and not t.startswith('['): lines.append(t)
    for line in lines:
        if '/' in line and ':' not in line and 'box /' not in line.lower() and 'teus' not in line.lower():
            item['voyage']=line; break
    for line in lines:
        u=line.upper()
        for label,key in [('ETA :','eta'),('ETB :','etb'),('ATB :','atb'),('ETD :','etd'),('ATD :','atd'),('Open Stack :','openStack'),('Closing Time :','closingTime')]:
            if u.startswith(label.upper()): item[key]=clean(line.split(':',1)[1]); break
        if 'BOOKING / OPEN / ACTUAL :' in u:
            p=[clean(x) for x in line.split(':',1)[1].split('/')]
            p=(p+['-','-','-'])[:3]
            item.update(booking=p[0],open=p[1],actual=p[2],bookingOpenActual=p)
        elif 'EXPORT BOX / TEUS :' in u: item['exportBoxTeus']=clean(line.split(':',1)[1])
        elif 'IMPORT BOX / TEUS :' in u: item['importBoxTeus']=clean(line.split(':',1)[1])
    for a in block.find_all('a',attrs={'data-url':True}):
        m=re.search(r'[?&]ves_id=([^&]+)',a.get('data-url',''))
        if m: item['vesId']=m.group(1); break
    for k in ('eta','etb','atb','etd','atd','openStack','closingTime','booking','open','actual','exportBoxTeus','importBoxTeus'):
        item.setdefault(k,'-')
    item.setdefault('bookingOpenActual',['-','-','-'])
    if history: item['history']=True
    return item

def parse_section(container,history=False):
    return [x for b in blocks(container) if (x:=parse_block(b,history)).get('vesselName')]

def section(soup,n):
    for sel in (f'.content_vessel._mCS_{n}',f'#mCSB_{n} .mCSB_container',f'#mCSB_{n}'):
        x=soup.select_one(sel)
        if x: return x
    return None

def extract_fragment(html: str, start_pattern: str, end_patterns: List[str]) -> str:
    """Extract one Pelindo section from raw HTML before BeautifulSoup parses it."""
    start = re.search(start_pattern, html, flags=re.I | re.S)
    if not start:
        return ""
    fragment = html[start.start():]
    end_positions = []
    for pattern in end_patterns:
        m = re.search(pattern, fragment, flags=re.I | re.S)
        if m:
            end_positions.append(m.start())
    if end_positions:
        fragment = fragment[:min(end_positions)]
    return fragment


def parse_raw_section(html: str, section_no: int) -> List[Dict[str, Any]]:
    # Raw extraction avoids relying on BeautifulSoup's recovery behaviour when
    # Pelindo's generated HTML contains nested/legacy markup.
    fragment = extract_fragment(
        html,
        rf'<div[^>]+class=["\'][^"\']*content_vessel[^"\']*_mCS_{section_no}[^"\']*["\'][^>]*>',
        [
            r'<!--\s*##########\s*CONFIRMED VESSEL',
            r'<!--\s*##########\s*Open Stack',
            r'<!--\s*##########\s*VESSEL SCHEDULE',
            r'<!--\s*##########\s*VESSEL HISTORY',
        ],
    )
    return parse_section(BeautifulSoup(fragment, 'html.parser')) if fragment else []


def scrape(html):
    # Parse the four primary sections from their actual Pelindo markers.
    alongside = parse_raw_section(html, 1)
    confirmed = parse_raw_section(html, 2)
    open_stack = parse_raw_section(html, 3)

    schedule_fragment = extract_fragment(
        html,
        r'<div[^>]+id=["\']div_ves_schedule["\'][^>]*>',
        [r'<!--\s*##########\s*VESSEL HISTORY'],
    )
    history_fragment = extract_fragment(
        html,
        r'<div[^>]+id=["\']div_ves_history["\'][^>]*>',
        [],
    )

    schedule = parse_section(BeautifulSoup(schedule_fragment, 'html.parser')) if schedule_fragment else []
    history = parse_section(BeautifulSoup(history_fragment, 'html.parser'), True) if history_fragment else []

    result = {
      'vesselAlongside': alongside,
      'confirmedVessel': confirmed,
      'openStack': open_stack,
      'vesselSchedule': schedule,
      'vesselHistory': history,
      'lastUpdated': datetime.now(timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M WIB'),
      'source': 'Pelindo TPKS Webaccess',
      'portalUrl': PORTAL_URL}
    logging.info('Alongside=%d Confirmed=%d OpenStack=%d Schedule=%d History=%d',
                 len(alongside),len(confirmed),len(open_stack),len(schedule),len(history))
    return result

def fetch(url):
    r=requests.get(url,headers={'User-Agent':'Mozilla/5.0 Chrome/120 Safari/537.36','Accept':'text/html,application/xhtml+xml'},timeout=30,verify=False)
    r.raise_for_status(); return r.text

def main():
    p=argparse.ArgumentParser(); p.add_argument('-i','--input',default=SOURCE_URL); p.add_argument('-o','--output',default='data.json'); a=p.parse_args()
    try:
        html=fetch(a.input) if a.input.startswith(('http://','https://')) else open(a.input,encoding='utf-8').read()
        with open(a.output,'w',encoding='utf-8') as f: json.dump(scrape(html),f,ensure_ascii=False,indent=2); f.write('\n')
    except Exception as e: logging.error('Scraper gagal: %s',e); sys.exit(1)
if __name__=='__main__': main()
