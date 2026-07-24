import pytest
from unittest.mock import AsyncMock
from fastapi import Request, HTTPException
from open_webui.models.config import Config
from filters import backend_check


async def test_inlet_models_found_success(httpx_mock):
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

    # Mock Config.get to return backends
    Config.get = AsyncMock(return_value=["http://backend.example.com"])

    # Mock httpx client to return models (success)
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": [{"id": "gpt-4"}]},
        status_code=200,
    )

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

    # Verify no metric upload occurred (no POST to pushgateway)
    post_requests = [r for r in requests if r.method == "POST"]
    assert len(post_requests) == 0


async def test_inlet_model_not_found_wait_enabled_scale_up_then_found(
    httpx_mock, caplog, mocker
):
    """Test inlet when model not found, wait enabled, scale up performed, then model found and body returned"""
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

    # Mock Config.get to return backends
    Config.get = AsyncMock(return_value=["http://backend.example.com"])

    # Mock httpx client responses:
    # First call: no models (scale up needed)
    # Second call: POST to pushgateway (scale up)
    # Third call (after short wait): models found
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": []},  # No models - trigger scale up
        status_code=200,
    )
    httpx_mock.add_response(
        url="http://pushgateway.prometheus.svc:9091/metrics/job/dynamo-gpt-4",
        method="POST",
        status_code=200,
        text="OK",
    )
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": [{"id": "gpt-4"}]},  # Models found after wait
        status_code=200,
    )

    # Mock asyncio.sleep to skip actual waiting
    mocker.patch("asyncio.sleep", return_value=None)

    # Call inlet with caplog to capture logs
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

    # Verify all requests were made
    requests = httpx_mock.get_requests()
    assert len(requests) == 3

    # First request: GET /models (no models)
    assert requests[0].method == "GET"
    assert "/models" in str(requests[0].url)

    # Second request: POST to pushgateway (scale up metric)
    assert requests[1].method == "POST"
    assert "/metrics/job/dynamo-gpt-4" in str(requests[1].url)

    # Third request: GET /models (models found)
    assert requests[2].method == "GET"
    assert "/models" in str(requests[2].url)

    # Verify scale up log message
    assert "Scale up request" in caplog.text
    # Verify models found after wait
    assert "Models available, breaking from wait loop" in caplog.text


async def test_inlet_model_not_found_wait_disabled_raises_exception(httpx_mock):
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

    # Mock Config.get to return backends
    Config.get = AsyncMock(return_value=["http://backend.example.com"])

    # Mock httpx client responses:
    # First call: no models (scale up needed)
    # Second call: POST to pushgateway (scale up happens even when not waiting)
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": []},  # No models
        status_code=200,
    )
    httpx_mock.add_response(
        url="http://pushgateway.prometheus.svc:9091/metrics/job/dynamo-gpt-4",
        method="POST",
        status_code=200,
        text="OK",
    )

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
    assert len(requests) == 2  # GET /models and POST to pushgateway

    # Verify scale up metric was sent
    assert requests[1].method == "POST"
    assert "/metrics/job/dynamo-gpt-4" in str(requests[1].url)


async def test_inlet_model_not_found_wait_enabled_scale_up_then_not_found_raises_exception(
    httpx_mock, caplog, mocker
):
    """Test inlet when model not found, wait enabled, scaled up, but model not found after wait, raises exception"""
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

    # Mock Config.get to return backends
    Config.get = AsyncMock(return_value=["http://backend.example.com"])

    # Mock httpx client responses:
    # First call: no models (scale up needed)
    # Second call: POST to pushgateway (scale up)
    # Remaining calls: still no models (wait timeout)
    httpx_mock.add_response(
        url="http://backend.example.com/models",
        method="GET",
        json={"data": []},  # No models - trigger scale up
        status_code=200,
    )
    httpx_mock.add_response(
        url="http://pushgateway.prometheus.svc:9091/metrics/job/dynamo-gpt-4",
        method="POST",
        status_code=200,
        text="OK",
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
    assert len(requests) == 5  # 1 initial GET + 1 POST + 3 wait loop GETs

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

    # Mock Config.get to return backends
    Config.get = AsyncMock(return_value=["http://backend.example.com"])

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


async def test_inlet_from_webui_returns_body(httpx_mock):
    """Test inlet when request is from WebUI, returns body directly without checking backend"""
    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"example.com")],
    }
    request = Request(scope=scope)

    # Set up metadata (from WebUI)
    metadata = {"interface": "open-webui"}

    # Set up model data
    model_data = {"id": "gpt-4", "urlIdx": 0}

    # Create filter instance
    filter_instance = backend_check.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Call inlet - should return body directly without making any requests
    result = await filter_instance.inlet(
        body=body,
        __user__=None,
        __metadata__=metadata,
        __request__=request,
        __model__=model_data,
    )

    # Verify the result is the same as the input body
    assert result == body

    # Verify no HTTP requests were made
    assert len(httpx_mock.get_requests()) == 0
