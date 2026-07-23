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


async def test_get_usage_top_level_usage(mocker):
    """Test that usage at the top level of body is returned correctly"""
    body = {
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150
        }
    }

    result = await accounting.get_usage(body)

    assert result == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150
    }


async def test_get_usage_message_usage(mocker):
    """Test that usage inside a message item is returned correctly"""
    body = {
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!", "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 80,
                "total_tokens": 200
            }}
        ]
    }

    result = await accounting.get_usage(body)

    assert result == {
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200
    }


async def test_get_usage_multiple_messages_with_usage(mocker):
    """Test that usage from the last message with usage is returned when multiple messages exist"""
    body = {
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!", "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 80,
                "total_tokens": 200
            }},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "I'm good!", "usage": {
                "prompt_tokens": 150,
                "completion_tokens": 90,
                "total_tokens": 240
            }}
        ]
    }

    result = await accounting.get_usage(body)

    assert result == {
        "prompt_tokens": 150,
        "completion_tokens": 90,
        "total_tokens": 240
    }


async def test_get_usage_no_usage_found(mocker):
    """Test that None is returned when no usage is found"""
    body = {
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
    }

    result = await accounting.get_usage(body)

    assert result is None


async def test_get_usage_with_response_message_id(mocker):
    """Test that usage from the specific response message ID is preferred"""
    body = {
        "id": "msg_123",
        "messages": [
            {"role": "user", "content": "Hello"},
            {"id": "msg_123", "role": "assistant", "content": "Hi there!", "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 80,
                "total_tokens": 200
            }},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "I'm good!"}
        ]
    }

    result = await accounting.get_usage(body)

    assert result == {
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200
    }
