# import base64
import os
import time
from pydantic import BaseModel, Field
from fastapi import Request, HTTPException, status
import httpx
import logging
from typing import Any
from filelock import AsyncFileLock, Timeout
from ldap3 import Server, Connection, ALL, ServerPool, FIRST
from ldap3.utils.conv import escape_filter_chars


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
        lock_dir: str = Field(
            default="/tmp",
            description="Directory for lock files",
        )
        # LDAP configuration for fallback verification
        ldap_urls: str = Field(
            default="",
            description="LDAP server URLs (e.g., ldap://ldap1.example.com,ldap://ldap2.example.com)",
        )
        ldap_base_dn: str = Field(
            default="dc=osc,dc=edu",
            description="Base DN for LDAP searches (e.g., dc=osc,dc=edu)",
        )
        ldap_user_dn: str = Field(
            default="ou=people,dc=osc,dc=edu",
            description="Base DN for LDAP user searches (e.g., ou=people,dc=osc,dc=edu)",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.logger = logging.getLogger("accounting")
        self.error_prefix = "process=accounting-error"
        self.metric_job = "k8-token-accounting"
        self.metric_name = "osc_k8_accounting_tokens_total"
        self.requests_metric_name = "osc_k8_accounting_requests_total"
        self.error_metric_job = "token-accounting-error"
        self.error_metric_name = "osc_k8_accounting_error"

    async def get_ldap_groups(self, username: str) -> list[str]:
        """
        Get all groups a user belongs to via LDAP.

        Args:
            username: The username to search for

        Returns:
            List of group names the user is a member of
        """
        if not self.valves.ldap_urls:
            self.logger.error("LDAP not configured, skipping membership check")
            return []

        groups = []
        try:
            # Connect to LDAP server
            pool = []
            for url in self.valves.ldap_urls.split(","):
                server = Server(url, get_info=ALL)
                pool.append(server)
            pool = ServerPool(pool, pool_strategy=FIRST, active=True)
            connection = Connection(server, auto_bind=False)

            # Try anonymous bind
            if not connection.bind():
                self.logger.error(
                    f"Failed to bind to LDAP server anonymously: {self.valves.ldap_urls}"
                )
                return []

            # Build user DN pattern (format: cn=<username>,ou=people,dc=osc,dc=edu)
            user_dn = f"cn={escape_filter_chars(username)},{self.valves.ldap_user_dn}"

            # Search for all posixGroup entries where user is a member
            group_filter = (
                f"(&(objectClass=posixGroup)(status=ACTIVE)(cn=P*)(member={user_dn}))"
            )

            connection.search(
                search_base=self.valves.ldap_base_dn,
                search_filter=group_filter,
                attributes=["cn"],
            )

            for entry in connection.entries:
                group_name = entry.cn
                groups.append(group_name)

            connection.unbind()
            return groups

        except Exception as e:
            self.logger.error(f"LDAP group lookup failed for user {username}: {e}")
            return []

    async def get_request_account(self, request: Request, user_name: str) -> str:
        request_host = request.url.hostname
        host_parts = request_host.split(".")
        account = None

        # Get user's LDAP groups
        ldap_groups = await self.get_ldap_groups(user_name)

        if len(host_parts) == 4:
            # Account from host
            account = host_parts[0].upper()
            # Validate account format (must start with capital P)
            if not account.startswith("P"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Request host {request_host} is not valid.  Must be in the format of <project>.<host>.osc.edu",
                )
        else:
            # No account in host, use LDAP groups to determine account
            if len(ldap_groups) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Request host {request_host} is not valid.  Must be in the format of <project>.<host>.osc.edu",
                )
            if len(ldap_groups) > 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Request host {request_host} is not valid.  Must be in the format of <project>.<host>.osc.edu",
                )
            account = ldap_groups[0]

        # Validate account is in user's LDAP groups
        if account not in ldap_groups:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Account {account} is not valid for user {user_name}",
            )
        return account

    async def get_metrics(self, instance: str) -> tuple[int, int]:
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
                    self.logger.debug(
                        f"job value not found in metric data, skip.  data={data}"
                    )
                    continue
                metric_instance = data.get("labels", {}).get("instance", None)
                if job != self.metric_job or metric_instance != instance:
                    self.logger.debug(
                        f"Skip metric job {job} instance {metric_instance}"
                    )
                    continue
                metric_data = data.get(self.metric_name, {})
                if metric_data:
                    metric = metric_data.get("metrics", [])[0]
                    metric_value = int(float(metric.get("value", 0)))
                    self.logger.debug(
                        f"Existing metric value. value={metric_value} data={data}"
                    )
                requests_data = data.get(self.requests_metric_name, {})
                if requests_data:
                    requests = requests_data.get("metrics", [])[0]
                    requests_value = int(float(requests.get("value", 0)))
                    self.logger.debug(
                        f"Existing requests value. value={requests_value} data={data}"
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
        # model_bytes = model.encode("utf-8")
        # model_base64 = base64.urlsafe_b64encode(model_bytes)
        # metric_model = model_base64.decode("utf-8")
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
        self.logger.debug(
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
            self.logger.debug(f"Metric sent: status={r.status_code} body={r.text}")

    async def send_error_metric(
        self,
        error: str,
    ) -> None:
        metric_data = f"""
# HELP {self.error_metric_name} K8 token accounting error
# TYPE {self.error_metric_name} gauge
{self.error_metric_name}{{error="{error}"}} 1
"""
        path = f"job/{self.error_metric_job}"
        metrics_url = f"{self.valves.pushgateway_url}/metrics/{path}"
        metrics_header = {"Content-Type": "text/plain"}
        self.logger.debug(f'Send error metric error="{error}" to {metrics_url}')
        async with httpx.AsyncClient() as client:
            r = await client.post(
                metrics_url, content=metric_data, headers=metrics_header
            )
            if not r.is_success:
                self.logger.error(
                    f'{self.error_prefix} msg="Unable to push error metric" status={r.status_code} body="{r.text}"'
                )
                return
            self.logger.debug(
                f"Error metric sent: status={r.status_code} body={r.text}"
            )

    async def inlet(
        self,
        body: dict,
        __user__: dict = None,
        __metadata__: dict = None,
        __request__: Request = None,
        __model__: dict = {},
    ) -> dict:
        self.logger.setLevel(getattr(logging, self.valves.log_level.upper()))
        user_name = (__user__ or {}).get("name")
        user_id = (__user__ or {}).get("id")
        self.logger.debug(f"Found user {user_name} and ID {user_id}")
        if not user_name or not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User name and User ID could not be determined",
            )
        account = await self.get_request_account(__request__, user_name)
        self.logger.debug(f"Found account {account}")

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
        self.logger.setLevel(getattr(logging, self.valves.log_level.upper()))
        error = None
        try:
            user_name = (__user__ or {}).get("name")
            user_id = (__user__ or {}).get("id")
            if not user_name or not user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User name and User ID could not be determined",
                )
            self.logger.debug(f"Found user {user_name} and ID {user_id}")
            account = await self.get_request_account(__request__, user_name)
            self.logger.debug(f"Found account {account}")

            chat_id = __metadata__.get("chat_id") or body.get("id", "unknown")
            model = __model__.get("id") if __model__ else body.get("model", "unknown")
            model_escaped = model.replace("/", "-")
            usage = await get_usage(body)
            self.logger.debug(f"Usage: chat-id={chat_id} model={model} usage={usage}")
            if usage is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Unable to get usage from response",
                )
            tokens = usage.get("total_tokens", None)
            if tokens is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Request lacks token usage in the response: {usage}",
                )

            instance = f"{model_escaped}-{account}-{user_name}"
            lock_file_path = os.path.join(self.valves.lock_dir, f"{instance}.lock")
            lock = AsyncFileLock(lock_file_path)
            async with lock:
                start_time = time.perf_counter()
                metric_value, requests_value = await self.get_metrics(instance=instance)
                metric_total = int(metric_value) + int(tokens)
                requests_total = int(requests_value) + 1
                self.logger.info(
                    f"Process token usage. user={user_name} account={account} model={model} tokens={tokens}"
                    + f" existing-value={metric_value} total-value={metric_total} existing-requests={requests_value} total-requests={requests_total}"
                )
                await self.send_metrics(
                    metric_value=metric_total,
                    requests_value=requests_total,
                    user_name=user_name,
                    account=account,
                    model=model,
                    instance=instance,
                )
                end_time = time.perf_counter()
                elapsed_time = end_time - start_time
                self.logger.debug(f"Metrics took {elapsed_time}")
        except Timeout:
            self.logger.error(
                f'{self.error_prefix} msg="Timeout waiting for lock" id={chat_id} user={user_name} account={account} model={model}'
            )
            error = "lock timeout"
        except HTTPException as e:
            self.logger.error(f'{self.error_prefix} msg="{e.detail}"')
            error = e.detail
        except Exception as e:
            self.logger.exception(
                f'{self.error_prefix} msg="An unhandled exception occurred {e}"'
            )
            error = "exception"
        finally:
            if error is not None:
                await self.send_error_metric(error=error)
        return body
