#!/usr/bin/env python3
"""Throwaway: what the facility search returns for the stations it missed."""
import json, time, urllib.request
B = 'https://publicfiles.fcc.gov'
H = {'User-Agent': 'louisiana-airwaves/1.0 (research)'}
for call in ['WVUE', 'WNOL', 'WLAE', 'WBRZ', 'WVLA', 'WGMB', 'KTBS', 'KTAL', 'KMSS',
             'KLFY', 'KADN', 'KNOE', 'KTVE', 'KALB', 'KLAX', 'WNTZ']:
    try:
        j = json.loads(urllib.request.urlopen(urllib.request.Request(
            f'{B}/api/service/facility/search/{call}', headers=H), timeout=30).read())
        tv = (j['results']['globalSearchResults'].get('tvFacilityList') or [])
        print(call, j['message'], [(f['callSign'], f['communityCity'], f['communityState'],
                                    f['service'], f['status'], f['id']) for f in tv][:6])
    except Exception as e:
        print(call, 'ERR', e)
    time.sleep(1)
