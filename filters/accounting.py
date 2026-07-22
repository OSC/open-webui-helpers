# import base64
import time
from pydantic import BaseModel, Field
from fastapi import Request, HTTPException, status
import httpx
import logging
from open_webui.models.groups import Groups
from typing import Any
from filelock import AsyncFileLock, Timeout


async def get_request_account(request: Request, user_id: str, user_name: str) -> str:
    request_host = request.url.hostname
    host_parts = request_host.split(".")
    account = None
    if len(host_parts) == 4:
        account = host_parts[0].upper()
    member_groups = await Groups.get_groups_by_member_id(user_id)
    group_names = [group.name for group in member_groups]
    if account is None:
        accounts = []
        for group in group_names:
            if group.startswith("P"):
                accounts.append(group)
        if len(accounts) == 0 or len(accounts) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Request host {request_host} is not valid.  Must be in the format of <project>.<host>.osc.edu",
            )
        account = accounts[0]
    if account not in group_names:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Account {account} is not valid for user {user_name}",
        )
    return account


# Logic from https://github.com/Skyzi000/open-webui-extensions/blob/main/functions/filter/token_usage_display.py
async def get_usage(body: dict[str, Any]) -> dict[str, Any] | None:
    usage = body.get("usage")
    if isinstance(usage, dict) and usage:
        return usage

    response_message_id = body.get("id")

    messages = body.get("messages")
    if isinstance(messages, list):
        # Prefer usage on the completed assistant message.
        if response_message_id is not None:
            for m in messages:
                if not isinstance(m, dict):
                    continue
                if m.get("id") != response_message_id:
                    continue
                u = m.get("usage")
                if isinstance(u, dict) and u:
                    return u

        # Fallback: last message that has usage.
        for m in reversed(messages):
            if not isinstance(m, dict):
                continue
            u = m.get("usage")
            if isinstance(u, dict) and u:
                return u

    return None


class Filter:
    class Valves(BaseModel):
        log_level: str = Field(default="INFO", description="Logging level")
        pushgateway_url: str = Field(
            default="http://pushgateway.prometheus.svc:9091",
            description="Push gateway URL",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.logger = logging.getLogger("accounting")
        self.metric_job = "k8-token-accounting"
        self.metric_name = "osc_k8_accounting_tokens_total"
        self.requests_metric_name = "osc_k8_accounting_requests_total"
        self.lockfile = "/tmp/accounting.lock"

    async def get_metrics(
        self, user_name: str, account: str, model: str, instance: str
    ) -> tuple[int, int]:
        headers = {
            "Content-Type": "application/json",
        }
        metrics_query_url = f"{self.valves.pushgateway_url}/api/v1/metrics"
        metrics = {}
        async with httpx.AsyncClient() as client:
            r = await client.get(metrics_query_url, headers=headers)
            if not r.is_success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unable to query existing accounting metrics. status={r.status_code} body={r.text}",
                )
            metrics = r.json()

        metric_value = 0
        requests_value = 0
        # Logic to query counter for increment left but unused
        if len(metrics.get("data", [])) > 0:
            for data in metrics["data"]:
                job = data.get("labels", {}).get("job", None)
                if job is None:
                    self.logger.info(
                        f"job value not found in metric data, skip.  data={data}"
                    )
                    continue
                metric_instance = data.get("labels", {}).get("instance", None)
                if job != self.metric_job and metric_instance != instance:
                    self.logger.info(
                        f"Skip metric job {job} instance {metric_instance}"
                    )
                    continue
                metric_data = data.get(self.metric_name, {})
                if metric_data:
                    metric = metric_data.get("metrics", [])[0]
                    metric_value = int(metric.get("value", 0))
                    self.logger.info(
                        f"Existing metric value. value={metric_value} user={user_name} account={account} model={model}"
                    )
                requests_data = data.get(self.requests_metric_name, {})
                if requests_data:
                    requests = requests_data.get("metrics", [])[0]
                    requests_value = int(requests.get("value", 0))
                    self.logger.info(
                        f"Existing requests value. value={requests_value} user={user_name} account={account} model={model}"
                    )
                if metric_data and requests_data:
                    break
        return int(metric_value), int(requests_value)

    async def send_metrics(
        self,
        metric_value: int,
        requests_value: int,
        user_name: str,
        account: str,
        model: str,
        instance: str,
    ) -> None:
        metric_data = f"""
# HELP {self.metric_name} K8 token accounting record
# TYPE {self.metric_name} counter
{self.metric_name}{{model="{model}",account="{account}",user="{user_name}"}} {metric_value}
# HELP {self.requests_metric_name} K8 requests accounting record
# TYPE {self.requests_metric_name} counter
{self.requests_metric_name}{{model="{model}",account="{account}",user="{user_name}"}} {requests_value}
"""
        path = f"job/{self.metric_job}/instance/{instance}"
        metrics_url = f"{self.valves.pushgateway_url}/metrics/{path}"
        metrics_header = {"Content-Type": "text/plain"}
        self.logger.info(
            f"Send metric value {metric_value} and requests value {requests_value} to {metrics_url}"
        )
        async with httpx.AsyncClient() as client:
            r = await client.post(
                metrics_url, content=metric_data, headers=metrics_header
            )
            if not r.is_success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unable to push accounting metric. status={r.status_code} body={r.text}",
                )
            self.logger.info(f"Metric sent: status={r.status_code} body={r.text}")

    async def inlet(
        self,
        body: dict,
        __user__: dict = None,
        __metadata__: dict = None,
        __request__: Request = None,
        __model__: dict = {},
    ) -> dict:
        user_name = (__user__ or {}).get("name")
        user_id = (__user__ or {}).get("id")
        self.logger.info(f"Found user {user_name} and ID {user_id}")
        if not user_name or not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User name and User ID could not be determined",
            )
        account = await get_request_account(__request__, user_id, user_name)
        self.logger.info(f"Found account {account}")

        # OpenAI-compatible streaming usage requires stream_options.include_usage=true.
        # Open WebUI may expose this as a per-model setting; we force it here to avoid
        # toggling it model-by-model.
        if body.get("stream") is True:
            stream_options = body.get("stream_options")
            if not isinstance(stream_options, dict):
                stream_options = {}
            if stream_options.get("include_usage") is not True:
                stream_options = {**stream_options, "include_usage": True}
                body = {**body, "stream_options": stream_options}

        return body

    async def outlet(
        self,
        body: dict,
        __user__: dict = None,
        __metadata__: dict = None,
        __request__: Request = None,
        __model__: dict = {},
    ) -> dict:
        try:
            user_name = (__user__ or {}).get("name")
            user_id = (__user__ or {}).get("id")
            if not user_name or not user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User name and User ID could not be determined",
                )
            self.logger.info(f"Found user {user_name} and ID {user_id}")
            account = await get_request_account(__request__, user_id, user_name)
            self.logger.info(f"Found account {account}")

            chat_id = __metadata__.get("chat_id") or body.get("id", "unknown")
            model = __model__.get("id") if __model__ else body.get("model", "unknown")
            usage = await get_usage(body)
            self.logger.info(f"Usage: chat-id={chat_id} model={model} usage={usage}")
            if usage is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Unable to get usage from response",
                )
            tokens = usage.get("total_tokens", None)
            if tokens is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Request lacks token usage in the response. usage={usage}",
                )
            self.logger.info(
                f"Process token usage. id={chat_id} user={user_name} account={account} model={model} tokens={tokens}"
            )

            instance = f"{model}-{account}-{user_name}"
            lock = AsyncFileLock(self.lockfile)
            async with lock:
                start_time = time.perf_counter()
                metric_value, requests_value = await self.get_metrics(
                    user_name=user_name, account=account, model=model, instance=instance
                )
                metric_value = int(metric_value) + int(tokens)
                requests_value = int(requests_value) + 1
                # model_bytes = model.encode("utf-8")
                # model_base64 = base64.urlsafe_b64encode(model_bytes)
                # metric_model = model_base64.decode("utf-8")
                await self.send_metrics(
                    metric_value=metric_value,
                    requests_value=requests_value,
                    user_name=user_name,
                    account=account,
                    model=model,
                    instance=instance,
                )
                end_time = time.perf_counter()
                elapsed_time = end_time - start_time
                self.logger.info(f"Metrics took {elapsed_time}")
        except Timeout:
            self.logger.error(
                f"Timeout waiting for lock id={chat_id} user={user_name} account={account} model={model}"
            )
        except Exception as e:
            self.logger.exception(f"An unhandled exception occurred {e}")
        return body
