"""Tiny CLI to chat with the trip concierge.

Usage:
    python run.py "3 nights in Kyoto, what should I do and what will it cost?"

Needs GOOGLE_API_KEY set (see .env.example). For a richer dev UI, run
`adk web` from the project root instead.
"""

import asyncio
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types

from trip_concierge import root_agent

APP = "trip_concierge"
USER = "local-user"


async def ask(prompt: str) -> None:
    runner = InMemoryRunner(agent=root_agent, app_name=APP)
    session = await runner.session_service.create_session(app_name=APP, user_id=USER)
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    async for event in runner.run_async(
        user_id=USER, session_id=session.id, new_message=message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(part.text, end="", flush=True)
    print()


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or "What are some good things to do in Lisbon?"
    asyncio.run(ask(prompt))
