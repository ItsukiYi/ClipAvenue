# -*- coding: utf-8 -*-
import json
p = r'D:\JianyingPro Drafts\AI切片测试-20260922\draft_content.json'
d = json.load(open(p, encoding='utf-8'))
print('canvas:', d['canvas_config'])
print('videos materials:', len(d['materials']['videos']))
print('texts materials:', len(d['materials']['texts']))
for i, t in enumerate(d['tracks']):
    segs = t.get('segments', [])
    print(f'track[{i}] type={t["type"]} segments={len(segs)}')
v = d['materials']['videos'][0]
print('video material:', v['path'], 'dur_µs:', v['duration'])
for s in d['tracks'][0]['segments']:
    print('  seg source:', s['source_timerange'], 'target:', s['target_timerange'])
for s in d['tracks'][1]['segments']:
    print('  text seg:', s.get('content', '')[:20], s['target_timerange'])