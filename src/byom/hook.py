"""LiteLLM proxy callback: rewrites the virtual `byom-active` model on every request."""

from __future__ import annotations

from litellm.integrations.custom_logger import CustomLogger

from .state import resolve


class ActiveModelHook(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        data["model"] = resolve(data.get("model"))
        return data


proxy_handler_instance = ActiveModelHook()
