from pydantic import BaseModel, Field
from fastapi import Request
from open_webui.models.config import Config
import logging


class Filter:
    class Valves(BaseModel):
        log_level: str = Field(default="INFO", description="Logging level")

    def __init__(self):
        self.valves = self.Valves()
        self.logger = logging.getLogger("api_usage")

    async def inlet(
        self,
        body: dict,
        __user__: dict = None,
        __metadata__: dict = None,
        __request__: Request = None,
        __model__: dict = {},
    ) -> dict:
        url_path = __request__.url.path if __request__ else "unknown"
        chat_id = __metadata__.get("chat_id") if __metadata__ else None
        user_name = __user__.get("name", "unknown") if __user__ else "anonymous"
        model = __model__.get("id") if __model__ else body.get("model", "unknown")

        idx = __model__.get("urlIdx", None) if __model__ else None
        backends = await Config.get("openai.api_base_urls") or []
        if idx is not None and len(backends) > 0:
            backend_url = backends[idx]
        else:
            backend_url = "unknown"
            self.logger.error(
                "Unable to determine model index", extra={"model_metadata": __model__}
            )

        self.logger.info(
            "Request",
            extra={
                "user": user_name,
                "path": url_path,
                "model": model,
                "backend": backend_url,
                "chat_id": chat_id or "none",
            },
        )

        return body
