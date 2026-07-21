import base64
from pydantic import BaseModel, Field
from fastapi import Request, HTTPException, status
import httpx
import logging
from open_webui.models.groups import Groups

async def get_request_account(request: Request, user_id: str, user_name: str) -> str:
    request_host = request.url.hostname
    host_parts = request_host.split(".")
    account = None
    if len(host_parts) == 4:
        account = host_parts[0].upper()
    member_groups = Groups.get_groups_by_member_id(user_id)
    group_names = [group.name for group in member_groups]
    if account is None:
        accounts = []
        for group in group_names:
            if group.startswith("P"):
                accounts.append(group)
        if len(accounts) == 0 or len(accounts) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                details=f"Request host {request_host} is not valid.  Must be in the format of <project>.<host>.osc.edu"
            )
        account = accounts[0]
    if account not in group_names:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            details=f"Account {account} is not valid for user {user_name}"
        )
    return account

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
        if not user_name or not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                details="User name and User ID could not be determined"
            )
        _ = await get_request_account(__request__, user_id, user_name)

        return body

    async def outlet(
        self,
        body: dict,
        __user__: dict = None,
        __metadata__: dict = None,
        __request__: Request = None,
        __model__: dict = {},
    ) -> dict:
        user_name = (__user__ or {}).get("name")
        user_id = (__user__ or {}).get("id")
        if not user_name or not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                details="User name and User ID could not be determined"
            )
        account = await get_request_account(__request__, user_id, user_name)

        model = __model__.get("id") if __model__ else body.get("model", "unknown")
        usage = body.get("usage", {})
        tokens = usage.get("total_tokens", None)
        if tokens is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                details=f"Request lacks token usage in the response. usage={usage}"
            )
        self.logger.info(
            f"Process token usage. user={user_name} account={account} model={model} tokens={tokens}"
        )

        headers = {
            "Content-Type": "application/json",
        }
        metric_job = "k8-token-accounting"
        metric_name = "osc_k8_token_accounting"
        metrics_query_url = f"{self.valves.pushgateway_url}/api/v1/metrics"
        metrics = None
        async with httpx.AsyncClient() as client:
            r = await client.get(metrics_query_url, headers=headers)
            if not r.is_success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    details=f"Unable to query existing accounting metrics. status={r.status_code} body={r.text}"
                )
            metrics = r.json()

        metric_value = 0
        if len(metrics.get("data", [])) > 0:
            for data in metrics["data"]:
                job = data.get("labels", {}).get("job", None)
                if job is None:
                    self.logger.info(
                        f"job value not found in metric data, skip.  data={data}"
                    )
                    continue
                if job != metric_job:
                    self.logger.info(
                        f"Skip metric job {job}"
                    )
                metric = data.get(metric_name, {})
                if not metric:
                    self.logger.info(
                        f"metric data for job {job} lacks metric {metric}.  data={data}"
                    )
                    continue
                for metric in metric.get("metrics", []):
                    labels = metric.get("labels", {})
                    if labels.get("user") != user_name:
                        continue
                    if labels.get("account") != account:
                        continue
                    if labels.get("model") != model:
                        continue
                    metric_value = int(metric.get("value", 0))
                    self.logger.info(
                        f"Existing metric value. value={metric_value} user={user_name} account={account} model={model} tokens={tokens}"
                    )
                    break
                if metric_value > 0:
                    break

        metric_value = metric_value = int(tokens)
        self.logger.info(
            f"New metric value. value={metric_value} user={user_name} account={account} model={model} tokens={tokens}"
        )
        model_bytes = model.encode('utf-8')
        model_base64 = base64.urlsafe_b64encode(model_bytes)
        metric_model = model_base64.decode('utf-8')
        metric_data = f"""
# HELP {metric_name} K8 token accounting record
# TYPE {metric_name} counter
{metric_name} {metric_value}
"""
        metrics_url = f"{self.valves.pushgateway_url}/metrics/job/{metric_job}/model@base64/{metric_model}/account/{account}/user/{user_name}"
        metrics_header = {"Content-Type": "text/plain"}
        self.logger.info(
            f"Send metric to {metrics_url}"
        )
        async with httpx.AsyncClient() as client:
            r = await client.post(
                metrics_url, content=metric_data, headers=metrics_header
            )
            if not r.is_success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    details=f"Unable to push accounting metric. status={r.status_code} body={r.text}"
                )
            self.logger.info(
                f"Metric sent: status={r.status_code} body={r.text}"
            )
        return body

