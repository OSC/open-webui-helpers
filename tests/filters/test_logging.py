from filters import logging

from fastapi import Request


async def test_inlet_successful_call(mocker, caplog):
    """Test successful inlet call with body returned"""
    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user"}

    # Set up metadata
    metadata = {"chat_id": "chat_123"}

    # Set up model data
    model_data = {"id": "gpt-4", "urlIdx": 0}

    # Create filter instance
    filter_instance = logging.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get to return backends
    from unittest.mock import AsyncMock
    from open_webui.models.config import Config

    Config.get = AsyncMock(return_value=["http://backend.example.com"])

    # Call inlet
    with caplog.at_level("INFO"):
        result = await filter_instance.inlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body
    assert result == body

    # Verify log message was produced
    assert "Request" in caplog.text
    assert caplog.records[0].user == "test_user"
    assert caplog.records[0].path == "/api/v1/chat"
    assert caplog.records[0].model == "gpt-4"
    assert caplog.records[0].backend == "http://backend.example.com"
    assert caplog.records[0].chat_id == "chat_123"


async def test_inlet_without_metadata(mocker, caplog):
    """Test inlet call without metadata"""
    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user"}

    # No metadata
    metadata = None

    # Set up model data
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = logging.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get to return backends
    from unittest.mock import AsyncMock
    from open_webui.models.config import Config

    Config.get = AsyncMock(return_value=["http://backend.example.com"])

    # Call inlet
    with caplog.at_level("INFO"):
        result = await filter_instance.inlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body
    assert result == body

    # Verify log message was produced
    assert "Request" in caplog.text
    assert caplog.records[1].user == "test_user"
    assert caplog.records[1].path == "/api/v1/chat"
    assert caplog.records[1].model == "gpt-4"
    assert caplog.records[1].backend == "unknown"
    assert caplog.records[1].chat_id == "none"


async def test_inlet_without_user(mocker, caplog):
    """Test inlet call without user data"""
    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com")],
    }
    request = Request(scope=scope)

    # No user data
    user_data = None

    # Set up metadata
    metadata = {"chat_id": "chat_123"}

    # Set up model data
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = logging.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get to return backends
    from unittest.mock import AsyncMock
    from open_webui.models.config import Config

    Config.get = AsyncMock(return_value=["http://backend.example.com"])

    # Call inlet
    with caplog.at_level("INFO"):
        result = await filter_instance.inlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body
    assert result == body

    # Verify log message was produced
    assert "Request" in caplog.text
    assert caplog.records[1].user == "anonymous"
    assert caplog.records[1].path == "/api/v1/chat"


async def test_inlet_without_model(mocker, caplog):
    """Test inlet call without model data"""
    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user"}

    # Set up metadata
    metadata = {"chat_id": "chat_123"}

    # No model data
    model_data = {}

    # Create filter instance
    filter_instance = logging.Filter()

    # Test body with model
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get to return backends
    from unittest.mock import AsyncMock
    from open_webui.models.config import Config

    Config.get = AsyncMock(return_value=["http://backend.example.com"])

    # Call inlet
    with caplog.at_level("INFO"):
        result = await filter_instance.inlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body
    assert result == body

    # Verify log message was produced
    assert "Request" in caplog.text
    assert caplog.records[1].user == "test_user"
    assert caplog.records[1].model == "gpt-4"


async def test_inlet_without_model_idx(mocker, caplog):
    """Test inlet call when model urlIdx is not available"""
    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user"}

    # Set up metadata
    metadata = {"chat_id": "chat_123"}

    # Model data without urlIdx
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = logging.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get to return backends
    from unittest.mock import AsyncMock
    from open_webui.models.config import Config

    Config.get = AsyncMock(return_value=["http://backend.example.com"])

    # Call inlet
    with caplog.at_level("INFO"):
        result = await filter_instance.inlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body
    assert result == body

    # Verify log message about unable to determine model index
    assert "Unable to determine model index" in caplog.text
    assert caplog.records[0].model_metadata == model_data


async def test_inlet_with_backend_url(mocker, caplog):
    """Test inlet call with model that has urlIdx"""
    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user"}

    # Set up metadata
    metadata = {"chat_id": "chat_123"}

    # Model data with urlIdx
    model_data = {"id": "gpt-4", "urlIdx": 1}

    # Create filter instance
    filter_instance = logging.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get to return backends
    from unittest.mock import AsyncMock
    from open_webui.models.config import Config

    Config.get = AsyncMock(
        return_value=["http://backend1.example.com", "http://backend2.example.com"]
    )

    # Call inlet
    with caplog.at_level("INFO"):
        result = await filter_instance.inlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body
    assert result == body

    # Verify log message with correct backend URL
    assert caplog.records[0].backend == "http://backend2.example.com"
