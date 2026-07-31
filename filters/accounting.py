# import base64
import os
import time
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from fastapi import Request, HTTPException, status
import httpx
import logging
from open_webui.models.groups import Groups
from open_webui.models.users import Users
from typing import Any
from filelock import AsyncFileLock, Timeout
from ldap3 import Server, Connection, ALL
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
        ldap_url: str = Field(
            default="",
            description="LDAP server URL (e.g., ldap://ldap.example.com)",
        )
        ldap_base_dn: str = Field(
            default="",
            description="Base DN for LDAP searches (e.g., dc=osc,dc=edu)",
        )
        ldap_member_attribute: str = Field(
            default="member",
            description="LDAP attribute containing group members",
        )
        ldap_user_attribute: str = Field(
            default="cn",
            description="LDAP attribute to match username",
        )
        ldap_inactive_threshold_days: int = Field(
            default=7,
            description="Days of inactivity before LDAP fallback",
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

    async def check_ldap_membership(self, username: str, group_name: str) -> bool:
        """
        Check if a user is a member of a group via LDAP.

        Args:
            username: The username to check
            group_name: The group name to check membership for

        Returns:
            True if user is a member of the group, False otherwise
        """
        if not self.valves.ldap_url or not self.valves.ldap_base_dn:
            self.logger.debug("LDAP not configured, skipping membership check")
            return False

        try:
            # Connect to LDAP server
            server = Server(self.valves.ldap_url, get_info=ALL)
            connection = Connection(server, auto_bind=False)

            # Try anonymous bind
            if not connection.bind():
                self.logger.warning(
                    f"Failed to bind to LDAP server anonymously: {self.valves.ldap_url}"
                )
                return False

            # Build search filter for the group (posixGroup object class)
            group_filter = f"(&(cn={escape_filter_chars(group_name)})(objectClass=posixGroup)(status=ACTIVE))"

            # Search for the group
            connection.search(
                search_base=self.valves.ldap_base_dn,
                search_filter=group_filter,
                attributes=[self.valves.ldap_member_attribute],
            )
            if not connection.entries:
                self.logger.debug(f"Group {group_name} not found in LDAP")
                connection.unbind()
                return False

            # Get the group entry
            group_entry = connection.entries[0]
            members = getattr(group_entry, self.valves.ldap_member_attribute, None)
            if not members:
                self.logger.debug(f"Group {group_name} has no members")
                connection.unbind()
                return False

            # Build user DN pattern (format: cn=<username>,ou=people,dc=osc,dc=edu)
            user_dn_pattern = (
                f"{self.valves.ldap_user_attribute}={escape_filter_chars(username)}"
            )

            # Check if any member matches the user
            self.logger.info(f"DEBUG group={group_name} class={type(members)}")
            for member in members.values:
                member_str = str(member)
                # Check if member DN contains the user attribute with the username
                if user_dn_pattern.lower() in member_str.lower():
                    self.logger.debug(
                        f"User {username} found in LDAP group {group_name}"
                    )
                    connection.unbind()
                    return True

            self.logger.debug(f"User {username} not found in LDAP group {group_name}")
            connection.unbind()
            return False

        except Exception as e:
            self.logger.error(
                f"LDAP membership check failed for user {username}, group {group_name}: {e}"
            )
            return False

    async def get_request_account(
        self, request: Request, user_id: str, user_name: str
    ) -> str:
        request_host = request.url.hostname
        host_parts = request_host.split(".")
        account = None
        if len(host_parts) == 4:
            account = host_parts[0].upper()
        member_groups = await Groups.get_groups_by_member_id(user_id)
        group_names = [group.name for group in member_groups]

        # Check if user is inactive and needs LDAP fallback
        user = await Users.get_user_by_id(user_id)
        is_inactive = False
        if user and user.last_active_at:
            last_active = datetime.fromtimestamp(user.last_active_at, tz=timezone.utc)
            threshold = datetime.now(timezone.utc) - timedelta(
                days=self.valves.ldap_inactive_threshold_days
            )
            if last_active < threshold:
                is_inactive = True
                self.logger.info(
                    f"User {user_name} is inactive (last active: {last_active}), will use LDAP fallback"
                )

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

        # For inactive users, verify account membership via LDAP
        if is_inactive and account not in group_names:
            self.logger.info(
                f"Account {account} not in user's groups, checking LDAP for {user_name}"
            )
            ldap_valid = await self.check_ldap_membership(user_name, account)
            if ldap_valid:
                self.logger.info(
                    f"LDAP confirmed user {user_name} is member of group {account}"
                )
                return account
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Account {account} is not valid for user {user_name} (neither in cached groups nor LDAP)",
                )

        if account not in group_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Account {account} is not valid for user {user_name}",
            )
        return account

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
                    self.logger.debug(
                        f"job value not found in metric data, skip.  data={data}"
                    )
                    continue
                metric_instance = data.get("labels", {}).get("instance", None)
                if job != self.metric_job and metric_instance != instance:
                    self.logger.debug(
                        f"Skip metric job {job} instance {metric_instance}"
                    )
                    continue
                metric_data = data.get(self.metric_name, {})
                if metric_data:
                    metric = metric_data.get("metrics", [])[0]
                    metric_value = int(metric.get("value", 0))
                    self.logger.debug(
                        f"Existing metric value. value={metric_value} user={user_name} account={account} model={model}"
                    )
                requests_data = data.get(self.requests_metric_name, {})
                if requests_data:
                    requests = requests_data.get("metrics", [])[0]
                    requests_value = int(requests.get("value", 0))
                    self.logger.debug(
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
        self.logger.info(f'Send error metric error="{error}" to {metrics_url}')
        async with httpx.AsyncClient() as client:
            r = await client.post(
                metrics_url, content=metric_data, headers=metrics_header
            )
            if not r.is_success:
                self.logger.error(
                    f'{self.error_prefix} msg="Unable to push error metric" status={r.status_code} body="{r.text}"'
                )
                return
            self.logger.info(f"Error metric sent: status={r.status_code} body={r.text}")

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
        account = await self.get_request_account(__request__, user_id, user_name)
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
        error = None
        try:
            user_name = (__user__ or {}).get("name")
            user_id = (__user__ or {}).get("id")
            if not user_name or not user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User name and User ID could not be determined",
                )
            self.logger.info(f"Found user {user_name} and ID {user_id}")
            account = await self.get_request_account(__request__, user_id, user_name)
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
                    detail=f"Request lacks token usage in the response: {usage}",
                )
            self.logger.info(
                f"Process token usage. id={chat_id} user={user_name} account={account} model={model} tokens={tokens}"
            )

            instance = f"{model}-{account}-{user_name}"
            lock_file_path = os.path.join(self.valves.lock_dir, f"{instance}.lock")
            lock = AsyncFileLock(lock_file_path, preserve_lock_file=False)
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
