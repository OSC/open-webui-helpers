from filters import accounting

import pytest
from fastapi import Request, HTTPException, status
from open_webui.models.groups import Groups, GroupModel
from filelock import Timeout


async def test_get_request_account_valid(mocker):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"PZS0708.chat.example.com")],
    }
    request = Request(scope=scope)
    groups = []
    groups.append(
        GroupModel(
            id="1",
            name="PZS0708",
            user_id="1",
            description="PZS0708",
            created_at=1,
            updated_at=1,
        )
    )
    groups.append(
        GroupModel(
            id="1",
            name="PZS0645",
            user_id="1",
            description="PZS0645",
            created_at=1,
            updated_at=1,
        )
    )
    groups.append(
        GroupModel(
            id="1",
            name="duo",
            user_id="1",
            description="duo",
            created_at=1,
            updated_at=1,
        )
    )
    mocker.patch.object(Groups, "get_groups_by_member_id", return_value=groups)

    result = await accounting.get_request_account(request, "user-id", "username")

    assert result == "PZS0708"


async def test_get_request_account_invalid(mocker):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"PDE0001.chat.example.com")],
    }
    request = Request(scope=scope)
    groups = []
    groups.append(
        GroupModel(
            id="1",
            name="PZS0708",
            user_id="1",
            description="PZS0708",
            created_at=1,
            updated_at=1,
        )
    )
    groups.append(
        GroupModel(
            id="1",
            name="PZS0645",
            user_id="1",
            description="PZS0645",
            created_at=1,
            updated_at=1,
        )
    )
    groups.append(
        GroupModel(
            id="1",
            name="duo",
            user_id="1",
            description="duo",
            created_at=1,
            updated_at=1,
        )
    )
    mocker.patch.object(Groups, "get_groups_by_member_id", return_value=groups)

    with pytest.raises(HTTPException, match="is not valid for user"):
        _ = await accounting.get_request_account(request, "user-id", "username")


async def test_get_request_account_no_url_single_project(mocker):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"chat.example.com")],
    }
    request = Request(scope=scope)
    groups = []
    groups.append(
        GroupModel(
            id="1",
            name="PZS0708",
            user_id="1",
            description="PZS0708",
            created_at=1,
            updated_at=1,
        )
    )
    groups.append(
        GroupModel(
            id="1",
            name="duo",
            user_id="1",
            description="duo",
            created_at=1,
            updated_at=1,
        )
    )
    mocker.patch.object(Groups, "get_groups_by_member_id", return_value=groups)

    result = await accounting.get_request_account(request, "user-id", "username")

    assert result == "PZS0708"


async def test_get_request_account_no_url_multiple_projects(mocker):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"chat.example.com")],
    }
    request = Request(scope=scope)
    groups = []
    groups.append(
        GroupModel(
            id="1",
            name="PZS0708",
            user_id="1",
            description="PZS0708",
            created_at=1,
            updated_at=1,
        )
    )
    groups.append(
        GroupModel(
            id="1",
            name="PZS0645",
            user_id="1",
            description="PZS0645",
            created_at=1,
            updated_at=1,
        )
    )
    groups.append(
        GroupModel(
            id="1",
            name="duo",
            user_id="1",
            description="duo",
            created_at=1,
            updated_at=1,
        )
    )
    mocker.patch.object(Groups, "get_groups_by_member_id", return_value=groups)

    with pytest.raises(HTTPException, match="Must be in the format of"):
        _ = await accounting.get_request_account(request, "user-id", "username")


async def test_get_usage_top_level_usage(mocker):
    """Test that usage at the top level of body is returned correctly"""
    body = {
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    }

    result = await accounting.get_usage(body)

    assert result == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
    }


async def test_get_usage_message_usage(mocker):
    """Test that usage inside a message item is returned correctly"""
    body = {
        "messages": [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": "Hi there!",
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 80,
                    "total_tokens": 200,
                },
            },
        ]
    }

    result = await accounting.get_usage(body)

    assert result == {
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200,
    }


async def test_get_usage_multiple_messages_with_usage(mocker):
    """Test that usage from the last message with usage is returned when multiple messages exist"""
    body = {
        "messages": [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": "Hi there!",
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 80,
                    "total_tokens": 200,
                },
            },
            {"role": "user", "content": "How are you?"},
            {
                "role": "assistant",
                "content": "I'm good!",
                "usage": {
                    "prompt_tokens": 150,
                    "completion_tokens": 90,
                    "total_tokens": 240,
                },
            },
        ]
    }

    result = await accounting.get_usage(body)

    assert result == {
        "prompt_tokens": 150,
        "completion_tokens": 90,
        "total_tokens": 240,
    }


async def test_get_usage_no_usage_found(mocker):
    """Test that None is returned when no usage is found"""
    body = {
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
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
            {
                "id": "msg_123",
                "role": "assistant",
                "content": "Hi there!",
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 80,
                    "total_tokens": 200,
                },
            },
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "I'm good!"},
        ],
    }

    result = await accounting.get_usage(body)

    assert result == {
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200,
    }


async def test_get_usage_non_dict_messages_with_response_id(mocker):
    """Test that get_usage handles non-dict messages with response_message_id set"""
    # This test specifically exercises the code path where response_message_id is set
    # and we iterate through messages that include non-dict entries
    body = {
        "id": "test",
        "messages": [
            {"role": "assistant", "content": "Hi", "id": "other_msg"},
            "not a dict",
            {"role": "user", "content": "Hello"},
            {
                "id": "msg_target",
                "role": "assistant",
                "content": "Target response",
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            },
        ],
    }

    result = await accounting.get_usage(body)

    assert result == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
    }


async def test_get_usage_non_dict_messages_without_response_id(mocker):
    """Test that get_usage handles non-dict messages with response_message_id set"""
    # This test specifically exercises the code path where response_message_id is not set
    # and we iterate through messages that include non-dict entries
    body = {
        "messages": [
            {"role": "assistant", "content": "Hi", "id": "other_msg"},
            {
                "id": "msg_target",
                "role": "assistant",
                "content": "Target response",
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            },
            "not a dict",
            {"role": "user", "content": "Hello"},
        ]
    }

    result = await accounting.get_usage(body)

    assert result == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
    }


async def test_get_usage_message_with_empty_usage(mocker):
    """Test that get_usage skips messages with empty or invalid usage"""
    body = {
        "messages": [
            {"role": "user", "content": "Hello", "usage": {}},
            {"role": "assistant", "content": "Hi", "usage": None},
            {"role": "assistant", "content": "Bye", "usage": "invalid"},
            {
                "id": "msg_123",
                "role": "assistant",
                "content": "Final",
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            },
        ]
    }

    result = await accounting.get_usage(body)

    assert result == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
    }


async def test_get_metrics_both_metrics_found(httpx_mock):
    """Test get_metrics when both metrics are found"""
    # Configure httpx_mock to return a successful response
    httpx_mock.add_response(
        url="http://pushgateway.prometheus.svc:9091/api/v1/metrics",
        json={
            "data": [
                {
                    "labels": {
                        "job": "k8-token-accounting",
                        "instance": "gpt-4-PZS0708-username",
                    },
                    "osc_k8_accounting_tokens_total": {"metrics": [{"value": "150"}]},
                    "osc_k8_accounting_requests_total": {"metrics": [{"value": "5"}]},
                }
            ]
        },
        status_code=200,
    )

    # Create filter instance
    filter_instance = accounting.Filter()

    # Call get_metrics
    result = await filter_instance.get_metrics(
        user_name="username",
        account="PZS0708",
        model="gpt-4",
        instance="gpt-4-PZS0708-username",
    )

    # Assert result
    assert result == (150, 5)


async def test_get_metrics_only_metric_name_found(httpx_mock):
    """Test get_metrics when only metric_name is found"""
    # Configure httpx_mock to return a successful response with only one metric
    httpx_mock.add_response(
        url="http://pushgateway.prometheus.svc:9091/api/v1/metrics",
        json={
            "data": [
                {
                    "labels": {
                        "job": "k8-token-accounting",
                        "instance": "gpt-4-PZS0708-username",
                    },
                    "osc_k8_accounting_tokens_total": {"metrics": [{"value": "200"}]},
                    # Missing osc_k8_accounting_requests_total
                }
            ]
        },
        status_code=200,
    )

    # Create filter instance
    filter_instance = accounting.Filter()

    # Call get_metrics
    result = await filter_instance.get_metrics(
        user_name="username",
        account="PZS0708",
        model="gpt-4",
        instance="gpt-4-PZS0708-username",
    )

    # Assert result - requests_value should default to 0
    assert result == (200, 0)


async def test_get_metrics_no_metrics_found(httpx_mock):
    """Test get_metrics when no metrics are found"""
    # Configure httpx_mock to return a successful response with no matching metrics
    httpx_mock.add_response(
        url="http://pushgateway.prometheus.svc:9091/api/v1/metrics",
        json={
            "data": [
                {
                    "labels": {"job": "other-job", "instance": "other-instance"},
                    "some_other_metric": {"metrics": [{"value": "100"}]},
                }
            ]
        },
        status_code=200,
    )

    # Create filter instance
    filter_instance = accounting.Filter()

    # Call get_metrics
    result = await filter_instance.get_metrics(
        user_name="username",
        account="PZS0708",
        model="gpt-4",
        instance="gpt-4-PZS0708-username",
    )

    # Assert result - both should default to 0
    assert result == (0, 0)


async def test_get_metrics_job_not_found_in_data(httpx_mock, caplog):
    """Test get_metrics when metric data doesn't have job field"""
    # Configure httpx_mock to return a response with data that lacks job field
    httpx_mock.add_response(
        url="http://pushgateway.prometheus.svc:9091/api/v1/metrics",
        json={
            "data": [
                {
                    "labels": {"instance": "gpt-4-PZS0708-username"},
                    # No job field - should skip this data
                    "osc_k8_accounting_tokens_total": {"metrics": [{"value": "150"}]},
                },
                {
                    "labels": {
                        "job": "k8-token-accounting",
                        "instance": "gpt-4-PZS0708-username",
                    },
                    "osc_k8_accounting_tokens_total": {"metrics": [{"value": "100"}]},
                    "osc_k8_accounting_requests_total": {"metrics": [{"value": "3"}]},
                },
            ]
        },
        status_code=200,
    )

    # Create filter instance
    filter_instance = accounting.Filter()

    # Call get_metrics
    with caplog.at_level("DEBUG"):
        result = await filter_instance.get_metrics(
            user_name="username",
            account="PZS0708",
            model="gpt-4",
            instance="gpt-4-PZS0708-username",
        )

    # Assert result - should get value from second data entry
    assert result == (100, 3)
    # Verify that the first entry was skipped due to missing job
    assert "job value not found in metric data" in caplog.text


async def test_get_metrics_client_not_successful(httpx_mock):
    """Test get_metrics when the client.get call is not successful"""
    # Configure httpx_mock to return an unsuccessful response
    httpx_mock.add_response(
        url="http://pushgateway.prometheus.svc:9091/api/v1/metrics",
        status_code=500,
        text="Internal Server Error",
    )

    # Create filter instance
    filter_instance = accounting.Filter()

    # Expect HTTPException to be raised
    with pytest.raises(
        HTTPException, match="Unable to query existing accounting metrics"
    ):
        await filter_instance.get_metrics(
            user_name="username",
            account="PZS0708",
            model="gpt-4",
            instance="gpt-4-PZS0708-username",
        )


async def test_send_metrics_success(httpx_mock):
    """Test send_metrics when the POST request is successful"""
    # Configure httpx_mock to return a successful response
    httpx_mock.add_response(
        url="http://pushgateway.prometheus.svc:9091/metrics/job/k8-token-accounting/instance/gpt-4-PZS0708-username",
        status_code=200,
        text="OK",
    )

    # Create filter instance
    filter_instance = accounting.Filter()

    # Call send_metrics
    await filter_instance.send_metrics(
        metric_value=150,
        requests_value=5,
        user_name="username",
        account="PZS0708",
        model="gpt-4",
        instance="gpt-4-PZS0708-username",
    )

    # Verify that the POST request was made with the correct data
    assert len(httpx_mock.get_requests()) == 1
    request = httpx_mock.get_requests()[0]
    assert request.method == "POST"
    assert (
        request.url
        == "http://pushgateway.prometheus.svc:9091/metrics/job/k8-token-accounting/instance/gpt-4-PZS0708-username"
    )
    assert request.headers["Content-Type"] == "text/plain"
    # Check that the payload contains the expected metric data (without strict whitespace matching)
    payload = request.content.decode()
    assert "# HELP osc_k8_accounting_tokens_total K8 token accounting record" in payload
    assert "# TYPE osc_k8_accounting_tokens_total counter" in payload
    assert (
        'osc_k8_accounting_tokens_total{model="gpt-4",account="PZS0708",user="username"} 150'
        in payload
    )
    assert (
        "# HELP osc_k8_accounting_requests_total K8 requests accounting record"
        in payload
    )
    assert "# TYPE osc_k8_accounting_requests_total counter" in payload
    assert (
        'osc_k8_accounting_requests_total{model="gpt-4",account="PZS0708",user="username"} 5'
        in payload
    )


async def test_send_metrics_failure(httpx_mock):
    """Test send_metrics when the POST request fails"""
    # Configure httpx_mock to return an unsuccessful response
    httpx_mock.add_response(
        url="http://pushgateway.prometheus.svc:9091/metrics/job/k8-token-accounting/instance/gpt-4-PZS0708-username",
        status_code=500,
        text="Internal Server Error",
    )

    # Create filter instance
    filter_instance = accounting.Filter()

    # Expect HTTPException to be raised
    with pytest.raises(HTTPException, match="Unable to push accounting metric"):
        await filter_instance.send_metrics(
            metric_value=150,
            requests_value=5,
            user_name="username",
            account="PZS0708",
            model="gpt-4",
            instance="gpt-4-PZS0708-username",
        )


async def test_send_error_metric_success(httpx_mock):
    """Test send_error_metric when the POST request is successful"""
    # Configure httpx_mock to return a successful response
    httpx_mock.add_response(
        url="http://pushgateway.prometheus.svc:9091/metrics/job/token-accounting-error",
        status_code=200,
        text="OK",
    )

    # Create filter instance
    filter_instance = accounting.Filter()

    # Call send_error_metric
    await filter_instance.send_error_metric(error="Test error message")

    # Verify that the POST request was made with the correct data
    assert len(httpx_mock.get_requests()) == 1
    request = httpx_mock.get_requests()[0]
    assert request.method == "POST"
    assert (
        request.url
        == "http://pushgateway.prometheus.svc:9091/metrics/job/token-accounting-error"
    )
    assert request.headers["Content-Type"] == "text/plain"
    # Check that the payload contains the expected metric data
    payload = request.content.decode()
    assert "# HELP osc_k8_accounting_error K8 token accounting error" in payload
    assert "# TYPE osc_k8_accounting_error gauge" in payload
    assert 'osc_k8_accounting_error{error="Test error message"} 1' in payload


async def test_send_error_metric_failure(httpx_mock, caplog):
    """Test send_error_metric when the POST request fails"""
    # Configure httpx_mock to return an unsuccessful response
    httpx_mock.add_response(
        url="http://pushgateway.prometheus.svc:9091/metrics/job/token-accounting-error",
        status_code=500,
        text="Internal Server Error",
    )

    # Create filter instance
    filter_instance = accounting.Filter()

    # Call send_error_metric - should not raise exception but log error
    with caplog.at_level("ERROR"):
        await filter_instance.send_error_metric(error="Test error message")

    # Verify the error message was logged for the push failure
    assert "Unable to push error metric" in caplog.text
    assert "status=500" in caplog.text
    assert 'body="Internal Server Error"' in caplog.text


async def test_inlet_successful_call(mocker):
    """Test successful inlet call with body returned"""
    # Mock the get_request_account function
    mock_get_request_account = mocker.patch("filters.accounting.get_request_account")

    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"PZS0708.chat.example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user", "id": "test_user_id"}

    # Set up model data
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = accounting.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock get_request_account to return a valid account
    mock_get_request_account.return_value = "PZS0708"

    # Call inlet
    result = await filter_instance.inlet(
        body=body, __user__=user_data, __request__=request, __model__=model_data
    )

    # Verify the result is the same as the input body
    assert result == body
    # Verify get_request_account was called
    mock_get_request_account.assert_called_once_with(
        request, "test_user_id", "test_user"
    )


async def test_inlet_stream_request_modified(mocker):
    """Test inlet with stream request where body is modified"""
    # Mock the get_request_account function
    mock_get_request_account = mocker.patch("filters.accounting.get_request_account")

    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"PZS0708.chat.example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user", "id": "test_user_id"}

    # Set up model data
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = accounting.Filter()

    # Test body with stream enabled but without include_usage
    body = {
        "model": "gpt-4",
        "stream": True,
        "messages": [{"role": "user", "content": "Hello"}],
    }

    # Mock get_request_account to return a valid account
    mock_get_request_account.return_value = "PZS0708"

    # Call inlet
    result = await filter_instance.inlet(
        body=body, __user__=user_data, __request__=request, __model__=model_data
    )

    # Verify that stream_options was added to the body
    assert result["stream"] is True
    assert "stream_options" in result
    assert result["stream_options"]["include_usage"] is True
    # Verify get_request_account was called
    mock_get_request_account.assert_called_once_with(
        request, "test_user_id", "test_user"
    )


async def test_inlet_user_missing_info(mocker):
    """Test inlet when user name or user id is missing"""
    # Mock the get_request_account function (should not be called)
    mock_get_request_account = mocker.patch("filters.accounting.get_request_account")

    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"PZS0708.chat.example.com")],
    }
    request = Request(scope=scope)

    # Set up incomplete user data (missing name)
    user_data = {"id": "test_user_id"}

    # Set up model data
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = accounting.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Call inlet - should raise HTTPException
    with pytest.raises(
        HTTPException, match="User name and User ID could not be determined"
    ):
        await filter_instance.inlet(
            body=body, __user__=user_data, __request__=request, __model__=model_data
        )

    # Verify get_request_account was not called
    mock_get_request_account.assert_not_called()


async def test_inlet_get_account_fails(mocker):
    """Test inlet when getting account fails"""
    # Mock the get_request_account function to raise an exception
    mock_get_request_account = mocker.patch("filters.accounting.get_request_account")

    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"PZS0708.chat.example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user", "id": "test_user_id"}

    # Set up model data
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = accounting.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock get_request_account to raise an exception
    mock_get_request_account.side_effect = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="Account not valid"
    )

    # Call inlet - should raise HTTPException from get_request_account
    with pytest.raises(HTTPException, match="Account not valid"):
        await filter_instance.inlet(
            body=body, __user__=user_data, __request__=request, __model__=model_data
        )

    # Verify get_request_account was called
    mock_get_request_account.assert_called_once_with(
        request, "test_user_id", "test_user"
    )


async def test_outlet_successful_call(mocker, caplog):
    """Test successful outlet call with body returned"""
    # Mock external functions
    mock_get_request_account = mocker.patch("filters.accounting.get_request_account")
    mock_get_usage = mocker.patch("filters.accounting.get_usage")
    mock_get_metrics = mocker.patch.object(accounting.Filter, "get_metrics")
    mock_send_metrics = mocker.patch.object(accounting.Filter, "send_metrics")
    mock_send_error_metric = mocker.patch.object(accounting.Filter, "send_error_metric")

    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"PZS0708.chat.example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user", "id": "test_user_id"}

    # Set up metadata
    metadata = {"chat_id": "chat_123"}

    # Set up model data
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = accounting.Filter()

    # Test body with usage data
    body = {
        "id": "msg_123",
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": "Hi there!",
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 80,
                    "total_tokens": 200,
                },
            },
        ],
    }

    # Mock external functions
    mock_get_request_account.return_value = "PZS0708"
    mock_get_usage.return_value = {
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200,
    }
    mock_get_metrics.return_value = (100, 5)  # (metric_value, requests_value)
    mock_send_metrics.return_value = None

    # Call outlet
    with caplog.at_level("INFO"):
        result = await filter_instance.outlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body
    assert result == body

    # Verify all external functions were called
    mock_get_request_account.assert_called_once_with(
        request, "test_user_id", "test_user"
    )
    mock_get_usage.assert_called_once_with(body)
    mock_get_metrics.assert_called_once_with(
        user_name="test_user",
        account="PZS0708",
        model="gpt-4",
        instance="gpt-4-PZS0708-test_user",
    )
    mock_send_metrics.assert_called_once_with(
        metric_value=300,  # 100 + 200
        requests_value=6,  # 5 + 1
        user_name="test_user",
        account="PZS0708",
        model="gpt-4",
        instance="gpt-4-PZS0708-test_user",
    )
    # Verify send_error_metric was NOT called on success
    mock_send_error_metric.assert_not_called()


async def test_outlet_user_missing_info(mocker, caplog):
    """Test outlet when user name or user id is missing"""
    # Mock get_request_account (should not be called)
    mock_get_request_account = mocker.patch("filters.accounting.get_request_account")
    mock_get_usage = mocker.patch("filters.accounting.get_usage")
    mock_send_error_metric = mocker.patch.object(accounting.Filter, "send_error_metric")

    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"PZS0708.chat.example.com")],
    }
    request = Request(scope=scope)

    # Set up incomplete user data (missing name)
    user_data = {"id": "test_user_id"}

    # Set up metadata
    metadata = {"chat_id": "chat_123"}

    # Set up model data
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = accounting.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Call outlet - should NOT raise HTTPException (caught and logged)
    with caplog.at_level("ERROR"):
        result = await filter_instance.outlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body (returned normally)
    assert result == body

    # Verify get_request_account was not called
    mock_get_request_account.assert_not_called()
    # Verify get_usage was not called
    mock_get_usage.assert_not_called()

    # Verify error message was logged
    assert "User name and User ID could not be determined" in caplog.text
    # Verify send_error_metric was called with the error
    mock_send_error_metric.assert_called_once_with(
        error="User name and User ID could not be determined"
    )


async def test_outlet_get_account_fails(mocker, caplog):
    """Test outlet when getting account fails"""
    # Mock get_request_account to raise an exception
    mock_get_request_account = mocker.patch("filters.accounting.get_request_account")
    mock_get_usage = mocker.patch("filters.accounting.get_usage")
    mock_send_error_metric = mocker.patch.object(accounting.Filter, "send_error_metric")

    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"PZS0708.chat.example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user", "id": "test_user_id"}

    # Set up metadata
    metadata = {"chat_id": "chat_123"}

    # Set up model data
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = accounting.Filter()

    # Test body
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock get_request_account to raise an exception
    mock_get_request_account.side_effect = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="Account not valid"
    )

    # Call outlet - should NOT raise HTTPException (caught and logged)
    with caplog.at_level("ERROR"):
        result = await filter_instance.outlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body (returned normally)
    assert result == body

    # Verify get_request_account was called
    mock_get_request_account.assert_called_once_with(
        request, "test_user_id", "test_user"
    )
    # Verify get_usage was not called
    mock_get_usage.assert_not_called()

    # Verify error message was logged
    assert "Account not valid" in caplog.text
    # Verify send_error_metric was called with the error
    mock_send_error_metric.assert_called_once_with(error="Account not valid")


async def test_outlet_usage_missing(mocker, caplog):
    """Test outlet when usage is missing"""
    # Mock external functions
    mock_get_request_account = mocker.patch("filters.accounting.get_request_account")
    mock_get_usage = mocker.patch("filters.accounting.get_usage")
    mock_send_error_metric = mocker.patch.object(accounting.Filter, "send_error_metric")

    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"PZS0708.chat.example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user", "id": "test_user_id"}

    # Set up metadata
    metadata = {"chat_id": "chat_123"}

    # Set up model data
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = accounting.Filter()

    # Test body without usage
    body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # Mock get_usage to return None
    mock_get_usage.return_value = None

    # Mock get_request_account to return a valid account
    mock_get_request_account.return_value = "PZS0708"

    # Call outlet - should NOT raise HTTPException (caught and logged)
    with caplog.at_level("ERROR"):
        result = await filter_instance.outlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body (returned normally)
    assert result == body

    # Verify get_request_account was called
    mock_get_request_account.assert_called_once_with(
        request, "test_user_id", "test_user"
    )
    # Verify get_usage was called
    mock_get_usage.assert_called_once_with(body)

    # Verify error message was logged
    assert "Unable to get usage from response" in caplog.text
    # Verify send_error_metric was called with the error
    mock_send_error_metric.assert_called_once_with(
        error="Unable to get usage from response"
    )


async def test_outlet_total_tokens_is_none(mocker, caplog):
    """Test outlet when usage is found but total_tokens is None"""
    # Mock external functions
    mock_get_request_account = mocker.patch("filters.accounting.get_request_account")
    mock_get_usage = mocker.patch("filters.accounting.get_usage")
    mock_send_error_metric = mocker.patch.object(accounting.Filter, "send_error_metric")

    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"PZS0708.chat.example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user", "id": "test_user_id"}

    # Set up metadata
    metadata = {"chat_id": "chat_123"}

    # Set up model data
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = accounting.Filter()

    # Test body with usage that has no total_tokens
    body = {
        "id": "msg_123",
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": "Hi there!",
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 80,
                    # No total_tokens
                },
            },
        ],
    }

    # Mock get_usage to return usage with no total_tokens
    mock_get_usage.return_value = {
        "prompt_tokens": 120,
        "completion_tokens": 80,
    }
    # Mock get_request_account to return a valid account
    mock_get_request_account.return_value = "PZS0708"

    # Call outlet - should NOT raise HTTPException (caught and logged)
    with caplog.at_level("ERROR"):
        result = await filter_instance.outlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body (returned normally)
    assert result == body

    # Verify get_request_account was called
    mock_get_request_account.assert_called_once_with(
        request, "test_user_id", "test_user"
    )
    # Verify get_usage was called
    mock_get_usage.assert_called_once_with(body)

    # Verify error message was logged
    assert "Request lacks token usage in the response" in caplog.text
    # Verify send_error_metric was called with the error (includes the usage dict)
    mock_send_error_metric.assert_called_once_with(
        error="Request lacks token usage in the response: {'prompt_tokens': 120, 'completion_tokens': 80}"
    )


async def test_outlet_get_metrics_fails(mocker, caplog):
    """Test outlet when get_metrics fails"""
    # Mock external functions
    mock_get_request_account = mocker.patch("filters.accounting.get_request_account")
    mock_get_usage = mocker.patch("filters.accounting.get_usage")
    mock_get_metrics = mocker.patch.object(accounting.Filter, "get_metrics")
    mock_send_metrics = mocker.patch.object(accounting.Filter, "send_metrics")
    mock_send_error_metric = mocker.patch.object(accounting.Filter, "send_error_metric")

    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"PZS0708.chat.example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user", "id": "test_user_id"}

    # Set up metadata
    metadata = {"chat_id": "chat_123"}

    # Set up model data
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = accounting.Filter()

    # Test body with usage data
    body = {
        "id": "msg_123",
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": "Hi there!",
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 80,
                    "total_tokens": 200,
                },
            },
        ],
    }

    # Mock external functions
    mock_get_request_account.return_value = "PZS0708"
    mock_get_usage.return_value = {
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200,
    }
    # Mock get_metrics to raise an exception
    mock_get_metrics.side_effect = HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database connection failed",
    )

    # Call outlet - should NOT raise HTTPException (caught and logged)
    with caplog.at_level("ERROR"):
        result = await filter_instance.outlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body (returned normally)
    assert result == body

    # Verify get_request_account was called
    mock_get_request_account.assert_called_once_with(
        request, "test_user_id", "test_user"
    )
    # Verify get_usage was called
    mock_get_usage.assert_called_once_with(body)
    # Verify get_metrics was called
    mock_get_metrics.assert_called_once_with(
        user_name="test_user",
        account="PZS0708",
        model="gpt-4",
        instance="gpt-4-PZS0708-test_user",
    )
    # Verify send_metrics was not called
    mock_send_metrics.assert_not_called()
    # Verify send_error_metric was called with the error
    mock_send_error_metric.assert_called_once_with(error="Database connection failed")

    # Verify error message was logged
    assert "Database connection failed" in caplog.text


async def test_outlet_send_metrics_fails(mocker, caplog):
    """Test outlet when send_metrics fails"""
    # Mock external functions
    mock_get_request_account = mocker.patch("filters.accounting.get_request_account")
    mock_get_usage = mocker.patch("filters.accounting.get_usage")
    mock_get_metrics = mocker.patch.object(accounting.Filter, "get_metrics")
    mock_send_metrics = mocker.patch.object(accounting.Filter, "send_metrics")
    mock_send_error_metric = mocker.patch.object(accounting.Filter, "send_error_metric")

    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"PZS0708.chat.example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user", "id": "test_user_id"}

    # Set up metadata
    metadata = {"chat_id": "chat_123"}

    # Set up model data
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = accounting.Filter()

    # Test body with usage data
    body = {
        "id": "msg_123",
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": "Hi there!",
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 80,
                    "total_tokens": 200,
                },
            },
        ],
    }

    # Mock external functions
    mock_get_request_account.return_value = "PZS0708"
    mock_get_usage.return_value = {
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200,
    }
    mock_get_metrics.return_value = (100, 5)  # (metric_value, requests_value)
    # Mock send_metrics to raise an exception
    mock_send_metrics.side_effect = HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Pushgateway connection failed",
    )

    # Call outlet - should not raise exception but log error
    with caplog.at_level("ERROR"):
        result = await filter_instance.outlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body
    assert result == body

    # Verify all external functions were called
    mock_get_request_account.assert_called_once_with(
        request, "test_user_id", "test_user"
    )
    mock_get_usage.assert_called_once_with(body)
    mock_get_metrics.assert_called_once_with(
        user_name="test_user",
        account="PZS0708",
        model="gpt-4",
        instance="gpt-4-PZS0708-test_user",
    )
    mock_send_metrics.assert_called_once_with(
        metric_value=300,  # 100 + 200
        requests_value=6,  # 5 + 1
        user_name="test_user",
        account="PZS0708",
        model="gpt-4",
        instance="gpt-4-PZS0708-test_user",
    )

    # Verify send_error_metric was called with the error
    mock_send_error_metric.assert_called_once_with(
        error="Pushgateway connection failed"
    )

    # Verify error message was logged
    assert "Pushgateway connection failed" in caplog.text


async def test_outlet_timeout_waiting_for_lock(mocker, caplog):
    """Test outlet when a Timeout exception occurs waiting for lock

    This test uses mock_lock to raise filelock.Timeout when entering the
    context manager, covering the Timeout exception handler at lines 300-304.
    We stub get_metrics to avoid network calls inside the lock context.
    """
    # Mock external functions
    mock_get_request_account = mocker.patch("filters.accounting.get_request_account")
    mock_get_usage = mocker.patch("filters.accounting.get_usage")
    mock_send_error_metric = mocker.patch.object(accounting.Filter, "send_error_metric")

    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"PZS0708.chat.example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user", "id": "test_user_id"}

    # Set up metadata
    metadata = {"chat_id": "chat_123"}

    # Set up model data
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = accounting.Filter()

    # Test body with usage data
    body = {
        "id": "msg_123",
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": "Hi there!",
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 80,
                    "total_tokens": 200,
                },
            },
        ],
    }

    # Mock external functions
    mock_get_request_account.return_value = "PZS0708"
    mock_get_usage.return_value = {
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200,
    }

    mocker.patch("filelock.AsyncFileLock.acquire", side_effect=Timeout("my_file.lock"))

    # Call outlet - should catch Timeout and log error
    with caplog.at_level("ERROR"):
        result = await filter_instance.outlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body (returned normally)
    assert result == body

    # Verify error message was logged for lock timeout
    assert "Timeout waiting for lock" in caplog.text
    # Verify send_error_metric was called with the error
    mock_send_error_metric.assert_called_once_with(error="lock timeout")


async def test_outlet_generic_exception(mocker, caplog):
    """Test outlet when an unhandled exception occurs"""
    # Mock external functions
    mock_get_request_account = mocker.patch("filters.accounting.get_request_account")
    mock_get_usage = mocker.patch("filters.accounting.get_usage")
    mock_send_error_metric = mocker.patch.object(accounting.Filter, "send_error_metric")

    # Set up mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [(b"host", b"PZS0708.chat.example.com")],
    }
    request = Request(scope=scope)

    # Set up user data
    user_data = {"name": "test_user", "id": "test_user_id"}

    # Set up metadata
    metadata = {"chat_id": "chat_123"}

    # Set up model data
    model_data = {"id": "gpt-4"}

    # Create filter instance
    filter_instance = accounting.Filter()

    # Test body with usage data
    body = {
        "id": "msg_123",
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Hello"},
            {
                "role": "assistant",
                "content": "Hi there!",
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 80,
                    "total_tokens": 200,
                },
            },
        ],
    }

    # Mock get_usage to return valid usage
    mock_get_usage.return_value = {
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200,
    }
    # Mock get_request_account to return a valid account
    mock_get_request_account.return_value = "PZS0708"
    # Mock get_metrics to raise a generic exception
    mock_get_metrics = mocker.patch.object(accounting.Filter, "get_metrics")
    mock_get_metrics.side_effect = ValueError("Unexpected error")
    # Mock the lock to avoid file system issues
    mock_lock = mocker.patch("filelock.AsyncFileLock")
    mock_lock_instance = mock_lock.return_value
    mock_lock_instance.__aenter__.return_value = None

    # Call outlet - should catch exception and log error
    with caplog.at_level("ERROR"):
        result = await filter_instance.outlet(
            body=body,
            __user__=user_data,
            __metadata__=metadata,
            __request__=request,
            __model__=model_data,
        )

    # Verify the result is the same as the input body (returned normally)
    assert result == body

    # Verify error message was logged
    assert "An unhandled exception occurred" in caplog.text
    # Verify send_error_metric was called with the error
    mock_send_error_metric.assert_called_once_with(error="exception")
