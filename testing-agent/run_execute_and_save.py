import requests, json, sys
payload = {'project_id':'live-run','srs':{'title':'demo'},'sdd':{'title':'demo'},'source_code':{'repo':'none'}}
try:
    r = requests.post('http://127.0.0.1:8085/testing/execute', json=payload, timeout=120)
    print('STATUS', r.status_code)
    with open('testing_execute_live.json','w', encoding='utf-8') as f:
        f.write(r.text)
    print('WROTE testing_execute_live.json')
    print(r.text[:1000])
except Exception as e:
    print('ERROR', e)
    sys.exit(1)
