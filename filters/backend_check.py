from pydantic import BaseModel, Field
from fastapi import Request, HTTPException, status
from open_webui.models.config import Config
import asyncio
import httpx
from loguru import logger
from opentelemetry import metrics

meter = metrics.get_meter("openwebui.custom.backend_check")
pending_request_metric = meter.create_gauge(
    name="dynamo.pending.request",
    description="Indicates if requests are pending (1 = pending, 0 = ok)",
    unit="1",
)


class Filter:
    class Valves(BaseModel):
        log_level: str = Field(default="INFO", description="Logging level")
        wait_header: str = Field(
            default="x-osc-wait",
            description="The header that determines if waiting for model",
        )
        wait_duration: int = Field(
            default=300, description="How long to wait for model to become available"
        )
        wait_users: list = Field(
            default=["oscchat"], description="List of users to enforce waiting."
        )
        k8_namespace: str = Field(default="dynamo", description="Kubernetes namespace")

    def __init__(self):
        self.valves = self.Valves()
        self.logger = logger

    async def inlet(
        self,
        body: dict,
        __user__: dict = None,
        __metadata__: dict = None,
        __request__: Request = None,
        __model__: dict = {},
    ) -> dict:
        idx = __model__.get("urlIdx", None)
        model = __model__.get("id") if __model__ else body.get("model", "unknown")
        metric_model = model.replace("/", "-")
        user_name = __user__.get("name", "unknown") if __user__ else "anonymous"
        values = await Config.get_many(
            "openai.api_base_urls", "openai.api_keys", "openai.api_configs"
        )
        backends = values.get("openai.api_base_urls") or []
        api_keys = values.get("openai.api_keys") or []
        api_configs = values.get("openai.api_configs") or {}
        backend_url = None
        if idx is not None and len(backends) > 0:
            backend_url = backends[idx]
        else:
            self.logger.bind(model_metadata=__model__).error(
                "Unable to determine model index."
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to determine backend URL",
            )
        unavailable = HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI backend is temporarily unavailable. Please try again later.",
            headers={"Retry-After": "120"},
        )
        headers = {
            "Content-Type": "application/json",
        }

        # Add Bearer token header if configured
        if idx is not None and len(api_keys) > idx:
            api_key = api_keys[idx]
            auth_config = api_configs.get(str(idx), {})
            auth_type = (
                auth_config.get("auth_type", "bearer")
                if isinstance(auth_config, dict)
                else "bearer"
            )

            if auth_type == "bearer" and api_key:
                headers["Authorization"] = f"Bearer {api_key}"
                self.logger.debug(
                    f"Bearer token authentication enabled for backend: backend={backend_url}"
                )

        models = None
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{backend_url}/models", headers=headers)
            if not r.is_success:
                raise unavailable
            models = r.json()

        # Exit early if backend models detected
        if len(models.get("data", [])) > 0:
            self.logger.debug(
                f"Models detected on backend, skipping scale up: backend={backend_url}"
            )
            pending_request_metric.set(
                0, {"model": metric_model, "namespace": self.valves.k8_namespace}
            )
            return body

        self.logger.bind(user=user_name, model=metric_model, backend=backend_url).info(
            "Scale up metric",
        )
        pending_request_metric.set(
            1, {"model": metric_model, "namespace": self.valves.k8_namespace}
        )
        wait = __request__.headers.get(self.valves.wait_header, "false")
        should_wait = False
        if wait.lower() == "true":
            should_wait = True
            self.logger.debug(
                f"{self.valves.wait_header} header is true, wait: wait-header={wait}"
            )
        if user_name in self.valves.wait_users:
            should_wait = True
            self.logger.debug(f"User {user_name} is a wait user, waiting")
        if not should_wait:
            self.logger.debug(
                f"{self.valves.wait_header} header is not true and not a wait user, skip wait, raise unavailable: wait-header={wait}"
            )
            raise unavailable

        delay = 10
        retries = self.valves.wait_duration // delay
        for attempt in range(1, retries + 1):
            self.logger.debug(f"Attempt {attempt} of {retries}...")
            wait_models = None
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{backend_url}/models", headers=headers)
                if not r.is_success:
                    raise unavailable
                wait_models = r.json()
            if len(wait_models.get("data", [])) > 0:
                self.logger.debug(
                    f"Models available, breaking from wait loop: backend={backend_url} models={wait_models}"
                )
                pending_request_metric.set(
                    0, {"model": metric_model, "namespace": self.valves.k8_namespace}
                )
                return body
            # Non-blocking pause allows other tasks to run in the background
            self.logger.debug(f"Waiting {delay} seconds before retrying...")
            await asyncio.sleep(delay)

        self.logger.bind(backend=backend_url).error("Model wait timed out")
        raise unavailable
