#!/usr/bin/env python

import os
import glob
import requests

url = os.getenv('WEBUI_URL').rstrip('/')
headers = {
    'Authorization': f'Bearer {os.getenv("WEBUI_TOKEN")}',
    'Content-Type': 'application/json'
}

functions = []
for filepath in glob.glob('filters/*.py'):
    filename = os.path.basename(filepath)
    func_id = filename.replace('.py', '')
    if func_id == "__init__":
        continue
    with open(filepath, 'r') as f:
        code_content = f.read()
    function = {
        'id': func_id,
        'name': func_id,
        'content': code_content
    }
    functions.append(function)

payload = {
    'functions': functions,
}
print("Syncing functions")
response = requests.post(
    f'{url}/api/v1/functions/sync', 
    headers=headers, 
    json=payload
)

if response.status_code not in [200, 201]:
    print(f'Failed to sync functions: {response.text}')
    exit(1)
