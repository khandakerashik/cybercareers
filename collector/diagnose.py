"""Non-destructive diagnostics for employer career pages.

Examples:
  python -m collector.diagnose --failed-only --limit 30
  python -m collector.diagnose --source "NCC Bank"

This command does not modify jobs.json, source_health.json or progress.json.
It observes the same host approval, robots policy, and pacing as the collector.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from .collect import DATA, CompliantFetcher, get_json, valid_url


def eligible(sources: list[dict], name: str = '', only_failed: bool = False) -> list[dict]:
    results = [s for s in sources if s.get('website') or s.get('careers_url')]
    results = [s for s in results if s.get('mode') not in ('restricted','link-only','directory','index')
               and s.get('sector') not in ('Job portal','Remote job feed','Social media')]
    if name:
        results = [s for s in results if name.casefold() in s.get('name','').casefold()]
    if only_failed:
        health=get_json(DATA/'source_health.json',{'sources':{}}).get('sources',{})
        results=[s for s in results if health.get(s.get('id'),{}).get('last_result') in ('failed','partial')]
    return results


def probe_source(source: dict, fetcher: CompliantFetcher) -> dict:
    urls=[]
    for url in [source.get('careers_url'),*(source.get('career_alternates') or []),source.get('website')]:
        if valid_url(url) and url not in urls:
            urls.append(url)
    attempts=[]
    success=False
    for url in urls:
        page=fetcher.fetch(url)
        good = page is not None
        attempts.append({'url':url, 'result':'reachable' if good else 'failed',
                         'detail':'HTML retrieved' if good else fetcher.failures.get(url,'Unavailable')})
        if good:
            success=True
            break
    state=('career_reachable' if success and attempts[-1]['url'] in
           [source.get('careers_url'),*(source.get('career_alternates') or [])]
           else 'homepage_only' if success else 'failed')
    return {'id':source.get('id'), 'source':source.get('name'), 'industry':source.get('sector'),
            'state':state, 'attempts':attempts, 'disclaimer':'Reachability only; not proof of an open cybersecurity job.'}


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description='Diagnose employer career sources without changing job data')
    parser.add_argument('--source',default='',help='Case-insensitive employer name (e.g. NCC Bank)')
    parser.add_argument('--failed-only',action='store_true',help='Test sources last seen as failed/limited')
    parser.add_argument('--limit',type=int,default=20,help='Maximum number of employers to test (1-50)')
    args=parser.parse_args(argv)
    if args.limit<1 or args.limit>50:parser.error('--limit must be between 1 and 50')
    sources=get_json(DATA/'sources.json',[])
    selected=eligible(sources,args.source,args.failed_only)[:args.limit]
    fetcher=CompliantFetcher(sources)
    report={'checked':0,'career_reachable':0,'homepage_only':0,'failed':0,'results':[]}
    for src in selected:
        result=probe_source(src,fetcher)
        report['checked']+=1
        report[result['state']]+=1
        report['results'].append(result)
        print(json.dumps(result,ensure_ascii=False),flush=True)
    print(json.dumps({'summary':{key:val for key,val in report.items() if key!='results'}},ensure_ascii=False),flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
