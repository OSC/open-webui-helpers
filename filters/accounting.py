import time
from pydantic import BaseModel, Field
from fastapi import Request, HTTPException, status
from loguru import logger
from opentelemetry import metrics
from typing import Any
from ldap3 import Server, Connection, ALL, ServerPool, FIRST
from ldap3.utils.conv import escape_filter_chars

meter = metrics.get_meter("openwebui.custom.accounting")

tokens_total_metric = meter.create_counter(
    name="osc.k8.accounting.tokens.total",
    description="Number of tokens used for OSC accounting",
    unit="1",
)
requests_total_metric = meter.create_counter(
    name="osc.k8.accounting.token.requests.total",
    description="Number of requests used for OSC accounting",
    unit="1",
)
error_metric = meter.create_gauge(
    name="osc.k8.accounting.tokens.error",
    description="Tracks whether an error recently occurred (1 = error, 0 = ok)",
    unit="1",
)


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
        self.logger = logger
        self.shared_users = ["oscchat"]
        self.username_header = "x-osc-user"
        self.error_tag = "accounting-error"

    async def get_username(self, __user__: dict, __request__: Request) -> str:
        username = (__user__ or {}).get("name")
        if username in self.shared_users:
            username = __request__.headers.get(self.username_header, None)
        return username

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

    async def inlet(
        self,
        body: dict,
        __user__: dict = None,
        __metadata__: dict = None,
        __request__: Request = None,
        __model__: dict = {},
    ) -> dict:
        user_name = await self.get_username(__user__=__user__, __request__=__request__)
        if not user_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User name and User ID could not be determined",
            )
        self.logger.debug(f"Found user {user_name}")
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
        error = None
        try:
            account = "N/A"
            chat_id = __metadata__.get("chat_id") or body.get("id", "unknown")
            model = __model__.get("id") if __model__ else body.get("model", "unknown")
            user_name = await self.get_username(
                __user__=__user__, __request__=__request__
            )
            if not user_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User name and User ID could not be determined",
                )
            self.logger.debug(f"Found user {user_name}")
            account = await self.get_request_account(__request__, user_name)
            self.logger.debug(f"Found account {account}")

            usage = await get_usage(body)
            self.logger.debug(f"Usage: chat-id={chat_id} model={model} usage={usage}")
            if usage is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Unable to get usage from response",
                )
            input_tokens = usage.get("prompt_tokens", None)
            output_tokens = usage.get("completion_tokens", None)
            if input_tokens is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Request lacks input token usage in the response: {usage}",
                )
            if "embed" in model.lower() and output_tokens is None:
                self.logger.debug(
                    f"Embed model {model} has no completion tokens, using output tokens 0"
                )
                output_tokens = 0
            if output_tokens is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Request lacks output token usage in the response: {usage}",
                )

            start_time = time.perf_counter()
            tokens_total_metric.add(
                int(input_tokens),
                {
                    "token_type": "input",
                    "user": user_name,
                    "account": account,
                    "model": model,
                },
            )
            tokens_total_metric.add(
                int(output_tokens),
                {
                    "token_type": "output",
                    "user": user_name,
                    "account": account,
                    "model": model,
                },
            )
            requests_total_metric.add(
                1, {"user": user_name, "account": account, "model": model}
            )
            self.logger.bind(
                user=user_name,
                account=account,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ).info("Process token usage.")
            end_time = time.perf_counter()
            elapsed_time = end_time - start_time
            self.logger.debug(f"Metrics took {elapsed_time}")
        except HTTPException as e:
            self.logger.bind(
                error_tag=self.error_tag,
                id=chat_id,
                user=user_name,
                account=account,
                model=model,
            ).error(e.detail)
            error = e.detail
        except Exception as e:
            self.logger.bind(
                error_tag=self.error_tag,
                id=chat_id,
                user=user_name,
                account=account,
                model=model,
            ).error(e)
            self.logger.bind(error_tag=self.error_tag).exception(
                f"An unhandled exception occurred {e}",
            )
            error = "exception"
        finally:
            if error is not None:
                error_metric.set(1, {"error": "error"})
        return body
