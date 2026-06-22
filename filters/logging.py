from pydantic import BaseModel, Field
from fastapi import Request
from typing import Optional
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
        # Check if request is from WebUI
        interface = __metadata__.get("interface") if __metadata__ else None
        url_path = __request__.url.path if __request__ else "unknown"
        chat_id = __metadata__.get("chat_id") if __metadata__ else None
        user_name = __user__.get("name", "unknown") if __user__ else "anonymous"
        model = __model__.get("id") if __model__ else body.get("model", "unknown")

        idx = __model__.get("urlIdx", None) if __model__ else None
        if idx is not None and __request__ is not None:
            backend_url = __request__.app.state.config.OPENAI_API_BASE_URLS[idx]
            # self.logger.info(f"Backend URL: {backend_url}")
        else:
            backend_url = "unknown"
            self.logger.info(
                f"Unable to determine model index. model-metadata={__model__}"
            )

        self.logger.info(
            f"Request: user={user_name} path={url_path} model={model} backend={backend_url} chat_id={chat_id or 'none'}"
        )

        return body

