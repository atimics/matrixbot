# Future Improvements

This document lists high level ideas for expanding the bot.

## Image Understanding
- Download images posted in rooms and pass them to an image captioning or analysis service.
- Expose a tool (e.g. `describe_last_image`) that the LLM can invoke to request
  a description of recent images.

## Dynamic Model Control
- Provide a tool that allows the LLM to switch between available models or
  request a specific model for a single turn.
- Persist the selected model per room so conversations can evolve using the most
  suitable LLM.

## Multi‑Account Swarm
- Support running multiple Matrix accounts simultaneously.
- Coordinate these accounts via the message bus so the system can act as a
  distributed swarm of bots.

These features will require additional design and testing but align with the
current asynchronous, event driven architecture.
