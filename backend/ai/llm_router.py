import os
from typing import List, Dict


class LLMRouter:

    def get_provider(self, model: str) -> str:
        if model.startswith("gemini"):
            return "gemini"
        elif model.startswith("gpt") or model.startswith("o1"):
            return "openai"
        elif model in ["llama3", "mistral", "codellama",
                       "phi3", "gemma"]:
            return "ollama"
        return "gemini"

    async def chat(
        self,
        messages: List[Dict],
        model: str = "gemini-1.5-flash",
        system_prompt: str = "",
        stream: bool = False
    ) -> str:
        provider = self.get_provider(model)
        if provider == "gemini":
            return await self._chat_gemini(
                messages, model, system_prompt)
        elif provider == "openai":
            return await self._chat_openai(
                messages, model, system_prompt)
        elif provider == "ollama":
            return await self._chat_ollama(
                messages, model, system_prompt)
        return "LLM provider not configured."

    async def _chat_gemini(self, messages, model, system_prompt):
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            return self._mock_response(messages)
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            gmodel = genai.GenerativeModel(
                model_name=model,
                system_instruction=system_prompt
            )
            history = []
            for m in messages[:-1]:
                history.append({
                    "role": "user" if m["role"] == "user"
                            else "model",
                    "parts": [m["content"]]
                })
            chat = gmodel.start_chat(history=history)
            response = chat.send_message(
                messages[-1]["content"])
            return response.text
        except Exception as e:
            return f"Gemini error: {str(e)}"

    async def _chat_openai(self, messages, model, system_prompt):
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return self._mock_response(messages)
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key)
            all_messages = []
            if system_prompt:
                all_messages.append(
                    {"role": "system", "content": system_prompt})
            all_messages.extend(messages)
            response = await client.chat.completions.create(
                model=model,
                messages=all_messages
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"OpenAI error: {str(e)}"

    async def _chat_ollama(self, messages, model, system_prompt):
        ollama_url = os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434")
        try:
            import httpx
            payload = {
                "model": model,
                "messages": messages,
                "stream": False
            }
            if system_prompt:
                payload["system"] = system_prompt
            async with httpx.AsyncClient(
                    timeout=60) as client:
                r = await client.post(
                    f"{ollama_url}/api/chat",
                    json=payload
                )
                return r.json()["message"]["content"]
        except Exception as e:
            return f"Ollama error: {str(e)}"

    def _mock_response(self, messages) -> str:
        last = messages[-1]["content"] if messages else ""
        return (
            f"[AI Mock] I received: '{last[:80]}...'\n"
            "Configure GEMINI_API_KEY, OPENAI_API_KEY, "
            "or OLLAMA_BASE_URL to enable real responses."
        )

    def build_system_prompt(self, context: dict) -> str:
        workspace = context.get("workspace_name", "None")
        environment = context.get("environment", "production")
        tools = context.get("tools", [])
        tool_list = ", ".join(tools) if tools else "none"
        base = f"""You are an AI assistant embedded in
Platform Assistant Portal, an internal developer platform.

Current context:
- Active Workspace: {workspace}
- Environment: {environment}
- Connected Tools: {tool_list}

You help engineers with:
- Checking tool health and connectivity
- Explaining infrastructure state
- Drafting runbooks and incident responses
- Summarizing alerts and metrics
- Suggesting workspace configurations

For actions that modify production systems,
always ask for confirmation before proceeding.
High-risk actions (HITL required) must be
explicitly approved by the user.

Be concise, technical, and accurate."""
        extra = ""
        ts = (context.get("tool_statuses_line") or "").strip()
        if ts:
            extra += f"\n\nTool statuses: {ts}"
        if context.get("production_operating"):
            extra += (
                "\n\n⚠️ You are operating in PRODUCTION.\n"
                "Treat all destructive actions as HITL-required."
            )
        return base + extra


llm_router = LLMRouter()
