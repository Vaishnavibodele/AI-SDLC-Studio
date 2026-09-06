from app.execution.controller import ExecutionController
from app.execution.modules import unit as unit_module

# Install a flaky run function
state = {'count':0}

def flaky(tc):
    state['count'] += 1
    if state['count'] < 3:
        return {'status':'ERROR','details':'transient'}
    return {'status':'PASS','details':'ok'}

unit_module.run = flaky

c = ExecutionController()
res = c.execute_test_case({'test_case_id':'DEMO-R','test_type':'unit','retry':2})
print(res)
