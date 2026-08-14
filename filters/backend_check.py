from pydantic import BaseModel, Field
from fastapi import Request, HTTPException, status
from open_webui.models.config import Config
import asyncio
import httpx
import logging


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
        pushgateway_url: str = Field(
            default="http://pushgateway.prometheus.svc:9091",
            description="Push gateway URL",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.logger = logging.getLogger("backend_check")

    async def inlet(
        self,
        body: dict,
        __user__: dict = None,
        __metadata__: dict = None,
        __request__: Request = None,
        __model__: dict = {},
    ) -> dict:
        idx = __model__.get("urlIdx", None)
        backends = await Config.get("openai.api_base_urls") or []
        backend_url = None
        if idx is not None and len(backends) > 0:
            backend_url = backends[idx]
        else:
            self.logger.error(
                "Unable to determine model index.", extra={"model_metadata": __model__}
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
            return body

        model = __model__.get("id") if __model__ else body.get("model", "unknown")
        metric_model = model.replace("/", "-")
        user_name = __user__.get("name", "unknown") if __user__ else "anonymous"
        metric_data = f"""
# HELP dynamo_pending_request Indicates a pending Dynamo request
# TYPE dynamo_pending_request gauge
dynamo_pending_request{{model="{metric_model}",namespace="{self.valves.k8_namespace}"}} 1
"""
        metrics_url = f"{self.valves.pushgateway_url}/metrics/job/{self.valves.k8_namespace}-{metric_model}"
        metrics_header = {"Content-Type": "text/plain"}
        self.logger.info(
            "Scale up request",
            extra={"user": user_name, "model": metric_model, "backend": backend_url},
        )
        async with httpx.AsyncClient() as client:
            r = await client.post(
                metrics_url, content=metric_data, headers=metrics_header
            )
            self.logger.debug(
                f"Scale up request completed (metric): status={r.status_code} body={r.text}"
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
                return body
            # Non-blocking pause allows other tasks to run in the background
            self.logger.debug(f"Waiting {delay} seconds before retrying...")
            await asyncio.sleep(delay)

        self.logger.error("Model wait timed out", extra={"backend": backend_url})
        raise unavailable

        # End logic, rest left in case becomes necessary in the future
        # Send request to trigger scale up
        self.logger.info(
            f"Scale up request: user={user_name} model={model} backend={backend_url}"
        )
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Scaling up, what is your name?"}],
        }
        # Run the query twice to ensure the metric gets triggered
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{backend_url}/chat/completions", json=payload)
            self.logger.info(
                f"Scale up request completed (first): status={r.status_code} body={r.text}"
            )
            await asyncio.sleep(2)
            r = await client.post(f"{backend_url}/chat/completions", json=payload)
            self.logger.info(
                f"Scale up request completed (second): status={r.status_code} body={r.text}"
            )

        # base_url = __request__.base_url
        # path_name = __request__.url.path
        # print(f"base_url={base_url} path_name={path_name}")

        # return body
