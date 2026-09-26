import pytest
from unittest.mock import AsyncMock
from fastapi import Request, HTTPException
from open_webui.models.config import Config
from filters import backend_check
from loguru import logger


async def test_inlet_models_found_success(httpx_mock, mocker):
    """Test inlet when models are found and success with body returned"""
    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com")],
    }
    request = Request(scope=scope)

    # Set up metadata (not from WebUI)
    metadata = {"interface": "api"}

    # Set up model data with urlIdx
    model_data = {"id": "gpt-4", "urlIdx": 0}

    # Create filter instance
    filter_instance = backend_check.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get_many to return backends, api_keys, and api_configs
    Config.get_many = AsyncMock(
        return_value={
            "openai.api_base_urls": ["http://backend.example.com"],
            "openai.api_keys": [],
            "openai.api_configs": {},
        }
    )

    # Mock httpx client to return models (success)
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": [{"id": "gpt-4"}]},
        status_code=200,
    )

    # Mock the metric to verify it's set to 0 (ok) when models are found
    mock_metric = mocker.patch.object(backend_check, "pending_request_metric")

    # Call inlet
    result = await filter_instance.inlet(
        body=body,
        __user__=None,
        __metadata__=metadata,
        __request__=request,
        __model__=model_data,
    )

    # Verify the result is the same as the input body
    assert result == body

    # Verify only one request was made (to check models)
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert "/models" in str(requests[0].url)

    # Verify pending_request_metric.set was called with value 0 (ok) since models were found
    mock_metric.set.assert_called_once_with(
        0, {"model": "gpt-4", "namespace": "dynamo"}
    )


async def test_inlet_model_not_found_wait_enabled_then_found(
    httpx_mock, caplog, mocker
):
    """Test inlet when model not found, wait enabled, then model found and body returned"""
    # Set up mock request with wait header
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com"), (b"x-osc-wait", b"true")],
    }
    request = Request(scope=scope)

    # Set up metadata (not from WebUI)
    metadata = {"interface": "api"}

    # Set up model data with urlIdx and user
    model_data = {"id": "gpt-4", "urlIdx": 0}
    user_data = {"name": "testuser"}

    # Create filter instance
    filter_instance = backend_check.Filter()
    # Stub timeout for testing - set short duration (30 seconds with 10-second delay = 3 retries)
    filter_instance.valves.wait_duration = 30

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get_many to return backends, api_keys, and api_configs
    Config.get_many = AsyncMock(
        return_value={
            "openai.api_base_urls": ["http://backend.example.com"],
            "openai.api_keys": [],
            "openai.api_configs": {},
        }
    )

    # Mock httpx client responses:
    # First call: no models (pending request)
    # Second call (after short wait): models found
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": []},  # No models - pending request
        status_code=200,
    )
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": [{"id": "gpt-4"}]},  # Models found after wait
        status_code=200,
    )

    # Mock asyncio.sleep to skip actual waiting
    mocker.patch("asyncio.sleep", return_value=None)

    # Mock the metric to capture set() calls
    mock_metric = mocker.patch.object(backend_check, "pending_request_metric")

    # Call inlet with caplog to capture logs
    with caplog.at_level("DEBUG"):
        result = await filter_instance.inlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body
    assert result == body

    # Verify all requests were made (only GET requests to /models)
    requests = httpx_mock.get_requests()
    assert len(requests) == 2

    # First request: GET /models (no models)
    assert requests[0].method == "GET"
    assert "/models" in str(requests[0].url)

    # Second request: GET /models (models found)
    assert requests[1].method == "GET"
    assert "/models" in str(requests[1].url)

    # Verify pending_request_metric.set was called with correct values
    # First call: set to 1 (pending) when no models found
    mock_metric.set.assert_any_call(1, {"model": "gpt-4", "namespace": "dynamo"})
    # Second call: set to 0 (ok) when models found
    mock_metric.set.assert_any_call(0, {"model": "gpt-4", "namespace": "dynamo"})

    # Verify models found after wait
    assert "Models available, breaking from wait loop" in caplog.text


async def test_inlet_model_not_found_oscchat_user_without_wait_header(
    httpx_mock, caplog, mocker
):
    """Test inlet when user is 'oscchat' (in wait_users), no x-osc-wait header, model not found initially, then model found"""
    # Set up mock request WITHOUT wait header
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com")],  # No x-osc-wait header
    }
    request = Request(scope=scope)

    # Set up metadata (not from WebUI)
    metadata = {"interface": "api"}

    # Set up model data with urlIdx and oscchat user
    model_data = {"id": "gpt-4", "urlIdx": 0}
    user_data = {"name": "oscchat"}  # User is in default wait_users list

    # Create filter instance
    filter_instance = backend_check.Filter()
    # Stub timeout for testing - set short duration (30 seconds with 10-second delay = 3 retries)
    filter_instance.valves.wait_duration = 30

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get_many to return backends, api_keys, and api_configs
    Config.get_many = AsyncMock(
        return_value={
            "openai.api_base_urls": ["http://backend.example.com"],
            "openai.api_keys": [],
            "openai.api_configs": {},
        }
    )

    # Mock httpx client responses:
    # First call: no models (pending request)
    # Second call (after short wait): models found
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": []},  # No models - pending request
        status_code=200,
    )
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": [{"id": "gpt-4"}]},  # Models found after wait
        status_code=200,
    )

    # Mock asyncio.sleep to skip actual waiting
    mocker.patch("asyncio.sleep", return_value=None)

    # Mock the metric to capture set() calls
    mock_metric = mocker.patch.object(backend_check, "pending_request_metric")

    # Call inlet with caplog to capture logs
    with caplog.at_level("DEBUG"):
        result = await filter_instance.inlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body
    assert result == body

    # Verify all requests were made (only GET requests to /models)
    requests = httpx_mock.get_requests()
    assert len(requests) == 2

    # First request: GET /models (no models)
    assert requests[0].method == "GET"
    assert "/models" in str(requests[0].url)

    # Second request: GET /models (models found)
    assert requests[1].method == "GET"
    assert "/models" in str(requests[1].url)

    # Verify pending_request_metric.set was called with correct values
    mock_metric.set.assert_any_call(1, {"model": "gpt-4", "namespace": "dynamo"})
    mock_metric.set.assert_any_call(0, {"model": "gpt-4", "namespace": "dynamo"})

    # Verify user is in wait_users log
    assert "User oscchat is a wait user, waiting" in caplog.text
    # Verify models found after wait
    assert "Models available, breaking from wait loop" in caplog.text


async def test_inlet_model_not_found_wait_disabled_raises_exception(httpx_mock, mocker):
    """Test inlet when model not found, wait disabled, so raises exception"""
    # Set up mock request without wait header
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com")],  # No x-osc-wait header
    }
    request = Request(scope=scope)

    # Set up metadata (not from WebUI)
    metadata = {"interface": "api"}

    # Set up model data with urlIdx and user not in wait_users
    model_data = {"id": "gpt-4", "urlIdx": 0}
    user_data = {"name": "otheruser"}  # Not in default wait_users list

    # Create filter instance
    filter_instance = backend_check.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get_many to return backends, api_keys, and api_configs
    Config.get_many = AsyncMock(
        return_value={
            "openai.api_base_urls": ["http://backend.example.com"],
            "openai.api_keys": [],
            "openai.api_configs": {},
        }
    )

    # Mock httpx client responses:
    # First call: no models (pending request)
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": []},  # No models
        status_code=200,
    )

    # Mock the metric to capture set() calls
    mock_metric = mocker.patch.object(backend_check, "pending_request_metric")

    # Call inlet - should raise HTTPException
    with pytest.raises(
        HTTPException, match="The AI backend is temporarily unavailable"
    ):
        await filter_instance.inlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify requests were made
    requests = httpx_mock.get_requests()
    assert len(requests) == 1  # Only GET /models

    # Verify request was to /models
    assert requests[0].method == "GET"
    assert "/models" in str(requests[0].url)

    # Verify pending_request_metric.set was called with value 1 (pending)
    mock_metric.set.assert_called_once_with(
        1, {"model": "gpt-4", "namespace": "dynamo"}
    )


async def test_inlet_model_not_found_wait_enabled_then_not_found_raises_exception(
    httpx_mock, caplog, mocker
):
    """Test inlet when model not found, wait enabled, but model not found after wait, raises exception"""
    # Set up mock request with wait header
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com"), (b"x-osc-wait", b"true")],
    }
    request = Request(scope=scope)

    # Set up metadata (not from WebUI)
    metadata = {"interface": "api"}

    # Set up model data with urlIdx and user
    model_data = {"id": "gpt-4", "urlIdx": 0}
    user_data = {"name": "testuser"}

    # Create filter instance
    filter_instance = backend_check.Filter()
    # Stub timeout for testing - set short duration (30 seconds with 10-second delay = 3 retries)
    filter_instance.valves.wait_duration = 30

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get_many to return backends, api_keys, and api_configs
    Config.get_many = AsyncMock(
        return_value={
            "openai.api_base_urls": ["http://backend.example.com"],
            "openai.api_keys": [],
            "openai.api_configs": {},
        }
    )

    # Mock httpx client responses:
    # First call: no models (pending request)
    # Remaining calls: still no models (wait timeout)
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": []},  # No models
        status_code=200,
    )
    # Add responses for the wait loop (3 retries for 30 second wait duration)
    for _ in range(3):
        httpx_mock.add_response(
            url="http://backend.example.com/models",
            method="GET",
            json={"data": []},  # Still no models
            status_code=200,
        )

    # Mock asyncio.sleep to skip actual waiting
    mocker.patch("asyncio.sleep", return_value=None)

    # Mock the metric to capture set() calls
    mock_metric = mocker.patch.object(backend_check, "pending_request_metric")

    # Call inlet - should raise HTTPException after wait timeout
    with caplog.at_level("INFO"):
        with pytest.raises(
            HTTPException, match="The AI backend is temporarily unavailable"
        ):
            await filter_instance.inlet(
                body=body,
                __user__=user_data,
                __metadata__=metadata,
                __request__=request,
                __model__=model_data,
            )

    # Verify all requests were made
    requests = httpx_mock.get_requests()
    assert len(requests) == 4  # 1 initial GET + 3 wait loop GETs

    # Verify pending_request_metric.set was called with value 1 (pending)
    mock_metric.set.assert_called_once_with(
        1, {"model": "gpt-4", "namespace": "dynamo"}
    )

    # Verify model wait timeout was logged
    assert "Model wait timed out" in caplog.text


async def test_inlet_query_models_fails_raises_exception(httpx_mock):
    """Test inlet when query of models fails and raises exception"""
    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com")],
    }
    request = Request(scope=scope)

    # Set up metadata (not from WebUI)
    metadata = {"interface": "api"}

    # Set up model data with urlIdx
    model_data = {"id": "gpt-4", "urlIdx": 0}

    # Create filter instance
    filter_instance = backend_check.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get_many to return backends, api_keys, and api_configs
    Config.get_many = AsyncMock(
        return_value={
            "openai.api_base_urls": ["http://backend.example.com"],
            "openai.api_keys": [],
            "openai.api_configs": {},
        }
    )

    # Mock httpx client to return 500 error on models query
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        status_code=500,
        text="Internal Server Error",
    )

    # Call inlet - should raise HTTPException
    with pytest.raises(
        HTTPException, match="The AI backend is temporarily unavailable"
    ):
        await filter_instance.inlet(
            body=body,
            __user__=None,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify request was made
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert "/models" in str(requests[0].url)


async def test_inlet_wait_loop_models_query_fails(httpx_mock, caplog, mocker):
    """Test inlet when wait loop models query fails - covers the wait loop's raise unavailable"""
    # Set up mock request with wait header
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com"), (b"x-osc-wait", b"true")],
    }
    request = Request(scope=scope)

    # Set up metadata (not from WebUI)
    metadata = {"interface": "api"}

    # Set up model data with urlIdx and user
    model_data = {"id": "gpt-4", "urlIdx": 0}
    user_data = {"name": "testuser"}

    # Create filter instance
    filter_instance = backend_check.Filter()
    # Stub timeout for testing - set short duration (30 seconds with 10-second delay = 3 retries)
    filter_instance.valves.wait_duration = 30

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get_many to return backends, api_keys, and api_configs
    Config.get_many = AsyncMock(
        return_value={
            "openai.api_base_urls": ["http://backend.example.com"],
            "openai.api_keys": [],
            "openai.api_configs": {},
        }
    )

    # Mock httpx client responses:
    # First call: no models (pending request)
    # Second call: GET /models - still no models
    # Third call: GET /models - fails with 500 error (this is the wait loop failure)
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": []},  # No models
        status_code=200,
    )
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": []},  # No models
        status_code=200,
    )
    # This call fails - covers the wait loop's raise unavailable
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        status_code=500,
        text="Internal Server Error",
    )

    # Mock asyncio.sleep to skip actual waiting
    mocker.patch("asyncio.sleep", return_value=None)

    # Mock the metric to capture set() calls
    mock_metric = mocker.patch.object(backend_check, "pending_request_metric")

    # Call inlet - should raise HTTPException after wait loop failure
    with caplog.at_level("INFO"):
        with pytest.raises(
            HTTPException, match="The AI backend is temporarily unavailable"
        ):
            await filter_instance.inlet(
                body=body,
                __user__=user_data,
                __metadata__=metadata,
                __request__=request,
                __model__=model_data,
            )

    # Verify all requests were made
    requests = httpx_mock.get_requests()
    assert len(requests) == 3  # 1 initial GET + 2 wait loop GETs

    # Verify pending_request_metric.set was called with value 1 (pending)
    mock_metric.set.assert_called_once_with(
        1, {"model": "gpt-4", "namespace": "dynamo"}
    )

    # Verify the last request was to /models and failed
    assert requests[-1].method == "GET"
    assert "/models" in str(requests[-1].url)


async def test_inlet_without_url_idx(mocker, caplog):
    """Test inlet when model doesn't have urlIdx - should raise HTTPException"""
    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com")],
    }
    request = Request(scope=scope)

    # Set up metadata (not from WebUI)
    metadata = {"interface": "api"}

    # Model data without urlIdx - this should trigger the "Unable to determine model index" log and raise exception
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = backend_check.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get_many to return backends, api_keys, and api_configs
    from unittest.mock import AsyncMock
    from open_webui.models.config import Config

    Config.get_many = AsyncMock(
        return_value={
            "openai.api_base_urls": ["http://backend.example.com"],
            "openai.api_keys": [],
            "openai.api_configs": {},
        }
    )
    bound_data = []

    def sink(message):
        bound_data.append(message.record["extra"])

    handler_id = logger.add(sink)

    try:
        # Call inlet - should raise HTTPException with "Unable to determine backend URL"
        with caplog.at_level("DEBUG"):
            with pytest.raises(HTTPException, match="Unable to determine backend URL"):
                await filter_instance.inlet(
                    body=body,
                    __user__=None,
                    __metadata__=metadata,
                    __request__=request,
                    __model__=model_data,
                )

        # Verify the warning was logged
        assert "Unable to determine model index" in caplog.text
        assert bound_data[0]["model_metadata"] == model_data
    finally:
        logger.remove(handler_id)


async def test_inlet_with_api_key_and_empty_configs_defaults_to_bearer(
    httpx_mock, caplog
):
    """Test inlet when api_keys is present but api_configs is empty, should default to auth_type=bearer"""
    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com")],
    }
    request = Request(scope=scope)

    # Set up metadata (not from WebUI)
    metadata = {"interface": "api"}

    # Set up model data with urlIdx
    model_data = {"id": "gpt-4", "urlIdx": 0}

    # Create filter instance
    filter_instance = backend_check.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get_many to return backends, api_keys (with value), and empty api_configs
    Config.get_many = AsyncMock(
        return_value={
            "openai.api_base_urls": ["http://backend.example.com"],
            "openai.api_keys": ["test-api-key-123"],
            "openai.api_configs": {},  # Empty dict - should default to bearer
        }
    )

    # Mock httpx client to return models (success)
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": [{"id": "gpt-4"}]},
        status_code=200,
    )

    # Call inlet with caplog to capture logs
    with caplog.at_level("DEBUG"):
        result = await filter_instance.inlet(
            body=body,
            __user__=None,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body
    assert result == body

    # Verify request was made with Authorization header
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert requests[0].headers.get("authorization") == "Bearer test-api-key-123"

    # Verify Bearer token authentication was logged
    assert "Bearer token authentication enabled" in caplog.text


async def test_inlet_with_api_key_and_bearer_auth_type(httpx_mock, caplog):
    """Test inlet when api_keys is present and api_configs explicitly sets auth_type=bearer"""
    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com")],
    }
    request = Request(scope=scope)

    # Set up metadata (not from WebUI)
    metadata = {"interface": "api"}

    # Set up model data with urlIdx
    model_data = {"id": "gpt-4", "urlIdx": 0}

    # Create filter instance
    filter_instance = backend_check.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock Config.get_many to return backends, api_keys, and api_configs with explicit bearer auth
    Config.get_many = AsyncMock(
        return_value={
            "openai.api_base_urls": ["http://backend.example.com"],
            "openai.api_keys": ["explicit-bearer-key-456"],
            "openai.api_configs": {
                "0": {"auth_type": "bearer"}
            },  # Explicitly set to bearer
        }
    )

    # Mock httpx client to return models (success)
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": [{"id": "gpt-4"}]},
        status_code=200,
    )

    # Call inlet with caplog to capture logs
    with caplog.at_level("DEBUG"):
        result = await filter_instance.inlet(
            body=body,
            __user__=None,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body
    assert result == body

    # Verify request was made with Authorization header
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert requests[0].headers.get("authorization") == "Bearer explicit-bearer-key-456"

    # Verify Bearer token authentication was logged
    assert "Bearer token authentication enabled" in caplog.text
