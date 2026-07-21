from filters import accounting

import pytest
from fastapi import Request, HTTPException
from open_webui.models.groups import Groups, GroupModel

async def test_get_request_account_valid(mocker):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/chat",
        "headers": [
            (b"host", b"PZS0708.chat.example.com")
        ],
    }
    request = Request(scope=scope)
    groups = []
    groups.append(GroupModel(id="1",name="PZS0708",user_id="1",description="PZS0708",created_at=1,updated_at=1))
    groups.append(GroupModel(id="1",name="PZS0645",user_id="1",description="PZS0645",created_at=1,updated_at=1))
    groups.append(GroupModel(id="1",name="duo",user_id="1",description="duo",created_at=1,updated_at=1))
    mocker.patch.object(Groups, 'get_groups_by_member_id', return_value=groups)

    result = await accounting.get_request_account(request, "user-id", "username")

    assert result == "PZS0708"

async def test_get_request_account_invalid(mocker):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/chat",
        "headers": [
            (b"host", b"PDE0001.chat.example.com")
        ],
    }
    request = Request(scope=scope)
    groups = []
    groups.append(GroupModel(id="1",name="PZS0708",user_id="1",description="PZS0708",created_at=1,updated_at=1))
    groups.append(GroupModel(id="1",name="PZS0645",user_id="1",description="PZS0645",created_at=1,updated_at=1))
    groups.append(GroupModel(id="1",name="duo",user_id="1",description="duo",created_at=1,updated_at=1))
    mocker.patch.object(Groups, 'get_groups_by_member_id', return_value=groups)

    with pytest.raises(HTTPException, match="is not valid for user"):
        _ = await accounting.get_request_account(request, "user-id", "username")

async def test_get_request_account_no_url_single_project(mocker):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/chat",
        "headers": [
            (b"host", b"chat.example.com")
        ],
    }
    request = Request(scope=scope)
    groups = []
    groups.append(GroupModel(id="1",name="PZS0708",user_id="1",description="PZS0708",created_at=1,updated_at=1))
    groups.append(GroupModel(id="1",name="duo",user_id="1",description="duo",created_at=1,updated_at=1))
    mocker.patch.object(Groups, 'get_groups_by_member_id', return_value=groups)

    result = await accounting.get_request_account(request, "user-id", "username")

    assert result == "PZS0708"

async def test_get_request_account_no_url_multiple_projects(mocker):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/chat",
        "headers": [
            (b"host", b"chat.example.com")
        ],
    }
    request = Request(scope=scope)
    groups = []
    groups.append(GroupModel(id="1",name="PZS0708",user_id="1",description="PZS0708",created_at=1,updated_at=1))
    groups.append(GroupModel(id="1",name="PZS0645",user_id="1",description="PZS0645",created_at=1,updated_at=1))
    groups.append(GroupModel(id="1",name="duo",user_id="1",description="duo",created_at=1,updated_at=1))
    mocker.patch.object(Groups, 'get_groups_by_member_id', return_value=groups)

    with pytest.raises(HTTPException, match="Must be in the format of"):
        _ = await accounting.get_request_account(request, "user-id", "username")
