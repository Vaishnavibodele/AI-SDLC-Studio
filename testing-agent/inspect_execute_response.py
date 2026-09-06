import json
fn='testing_execute_live.json'
with open(fn, 'r', encoding='utf-8') as f:
    j=json.load(f)
print('project_id', j.get('project_id'))
print('summary', j.get('execution_summary'))
for r in j.get('results',[]):
    if r.get('test_case_id')=='TC-007':
        print('\nTC-007:', json.dumps(r, indent=2)[:4000])
        break
else:
    print('TC-007 not found')
