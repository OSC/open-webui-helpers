#!/usr/bin/env python

import os
import glob
import requests
import time

url = os.getenv('WEBUI_URL').rstrip('/')
headers = {
    'Authorization': f'Bearer {os.getenv("WEBUI_TOKEN")}',
    'Content-Type': 'application/json'
}
version = os.getenv('VERSION')
FUNC_TYPES = {
    'filters': 'filter',
}

# First, query existing functions to preserve created_at timestamps
print("Fetching existing functions...")
response = requests.get(
    f'{url}/api/v1/functions/list',
    headers=headers
)

if response.status_code not in [200, 201]:
    print(f'Failed to fetch functions: {response.text}')
    exit(1)

existing_functions = response.json()
# Create a mapping of function id -> created_at
created_at_map = {func['id']: func['created_at'] for func in existing_functions}

functions = []
for filepath in glob.glob('filters/*.py'):
    filename = os.path.basename(filepath)
    func_id = filename.replace('.py', '')
    func_type = FUNC_TYPES[os.path.basename(os.path.dirname(filepath))]
    if func_id == "__init__":
        continue
    with open(filepath, 'r') as f:
        code_content = f.read()

    # Preserve created_at from existing function, or use current time if new
    created_at = created_at_map.get(func_id, int(time.time()))

    # Query existing valves only if function already exists
    valves = {}
    if func_id in created_at_map:
        print(f"Fetching valves for {func_id}...")
        response = requests.get(
            f'{url}/api/v1/functions/id/{func_id}/valves',
            headers=headers
        )
        if response.status_code not in [200, 201]:
            print(f'Failed to fetch valves for {func_id}: {response.text}')
            exit(1)
        valves = response.json()

    function = {
        'id': func_id,
        'name': func_id,
        'type': func_type,
        'meta': {
            'description': f"{func_id} version={version}",
        },
        'content': code_content,
        'created_at': created_at,
        'updated_at': int(time.time()),
        'valves': valves,
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
    # Parse and clean the error response
    error_data = response.json()
    if 'detail' in error_data and isinstance(error_data['detail'], list):
        # Remove 'input' key from each item in detail array
        cleaned_detail = []
        for item in error_data['detail']:
            cleaned_item = {k: v for k, v in item.items() if k != 'input'}
            cleaned_detail.append(cleaned_item)
        error_data['detail'] = cleaned_detail
        print(f'Failed to sync functions: {error_data}')
    else:
        print(f'Failed to sync functions: {error_data}')
    exit(1)
