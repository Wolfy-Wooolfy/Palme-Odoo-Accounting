"""AI assistant — GPT-4o-mini tool-call loop over read-only report services."""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from api.config import settings
from api.models.chat import ChatRequest, ChatResponse, ToolCall
from api.services.ai_tools import TOOL_SCHEMAS, execute_tool, summarize_tool_result

_SYSTEM_PROMPT = """\
You are Palme Finance Assistant, a read-only AI analyst embedded in Palme Finance — \
an Odoo 17 financial reporting dashboard for Palme Group.

Rules:
- Always respond in the same language the user wrote in (Arabic or English).
- You are STRICTLY read-only. Never suggest creating, editing, or deleting data.
- Use the provided tools to fetch real data before answering financial questions.
  Do not fabricate numbers. If a tool returns an error, say so clearly.
- Keep answers concise, well-structured, and in plain language.
- When showing financial figures, always mention the currency context if known.
- If the user asks about today's date or a "current" period, use: {today}

Default behaviour when dates are not specified by the user:
  Use date_from = first day of current month, date_to = {today}.
"""


def _build_system_prompt() -> str:
    today = date.today().isoformat()
    return _SYSTEM_PROMPT.format(today=today)


def _history_to_openai(request: ChatRequest) -> list[dict]:
    """Convert our ChatMessage history into OpenAI messages format."""
    messages: list[dict] = [{"role": "system", "content": _build_system_prompt()}]

    for msg in request.history:
        if msg.role == "user":
            messages.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant":
            messages.append({"role": "assistant", "content": msg.content})
        # Skip tool messages from history — they are already summarised in badges

    # Append the current user message
    messages.append({"role": "user", "content": request.message})
    return messages


def chat(request: ChatRequest, client) -> ChatResponse:
    """Run the GPT-4o-mini tool-call loop and return the assistant reply."""
    if not settings.openai_api_key:
        raise RuntimeError("AI assistant is not configured (OPENAI_API_KEY not set)")

    from openai import OpenAI  # lazy import — only when actually used

    oai = OpenAI(api_key=settings.openai_api_key)
    messages = _history_to_openai(request)

    executed_tools: list[ToolCall] = []
    max_iterations = settings.ai_max_tool_iterations

    for _ in range(max_iterations):
        response = oai.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            max_tokens=settings.ai_max_tokens,
            temperature=settings.ai_temperature,
        )

        choice = response.choices[0]
        finish_reason = choice.finish_reason
        assistant_msg = choice.message

        # Add assistant turn to the running messages
        messages.append(assistant_msg.model_dump(exclude_none=True))

        if finish_reason == "tool_calls" and assistant_msg.tool_calls:
            tool_results: list[dict] = []

            for tc in assistant_msg.tool_calls:
                name = tc.function.name
                try:
                    arguments: dict[str, Any] = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                result = execute_tool(name, arguments, client)
                summary = summarize_tool_result(name, result if isinstance(result, dict) else {"_list": result})

                executed_tools.append(ToolCall(name=name, arguments=arguments, result_summary=summary))

                # Feed result back as a tool message
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                })

            messages.extend(tool_results)

        else:
            # No more tool calls — final reply
            reply = assistant_msg.content or ""
            return ChatResponse(reply=reply, tool_calls=executed_tools)

    # Safety: if we exhaust iterations without a final answer
    return ChatResponse(
        reply="I reached the maximum number of data lookups. Please try a more specific question.",
        tool_calls=executed_tools,
    )
