"""Test data factories using factory_boy for consistent test data generation."""

import factory
from factory import Faker
from datetime import datetime, timezone
import uuid

from event_definitions import (
    MatrixMessageReceivedEvent,
    MatrixImageReceivedEvent,
    OpenRouterInferenceRequestEvent,
    OpenRouterInferenceResponseEvent,
    OllamaInferenceRequestEvent,
    OllamaInferenceResponseEvent,
    AIInferenceResponseEvent,
    ExecuteToolRequest,
    ToolExecutionResponse,
    ToolCall,
    ToolFunction,
    SendMatrixMessageCommand,
    SendReplyCommand,
    ReactToMessageCommand,
    SetTypingIndicatorCommand,
    ProcessMessageBatchCommand,
    ActivateListeningEvent,
    BotDisplayNameReadyEvent,
    HistoricalMessage,
    BatchedUserMessage,
    ToolRoleMessage
)


class MatrixMessageReceivedEventFactory(factory.Factory):
    class Meta:
        model = MatrixMessageReceivedEvent

    room_id = factory.Sequence(lambda n: f"!room{n}:matrix.example.com")
    event_id_matrix = factory.Sequence(lambda n: f"$event{n}:matrix.example.com")
    sender_id = factory.Sequence(lambda n: f"@user{n}:matrix.example.com")
    sender_display_name = Faker('name')
    body = Faker('text', max_nb_chars=200)
    room_display_name = Faker('word')
    timestamp = factory.LazyFunction(lambda: datetime.now(timezone.utc).timestamp())


class MatrixImageReceivedEventFactory(factory.Factory):
    class Meta:
        model = MatrixImageReceivedEvent

    room_id = factory.Sequence(lambda n: f"!room{n}:matrix.example.com")
    event_id_matrix = factory.Sequence(lambda n: f"$event{n}:matrix.example.com")
    sender_id = factory.Sequence(lambda n: f"@user{n}:matrix.example.com")
    sender_display_name = Faker('name')
    image_url = factory.Sequence(lambda n: f"mxc://matrix.example.com/image{n}")
    image_filename = Faker('file_name', extension='jpg')
    image_mimetype = "image/jpeg"
    room_display_name = Faker('word')
    timestamp = factory.LazyFunction(lambda: datetime.now(timezone.utc).timestamp())


class ToolFunctionFactory(factory.Factory):
    class Meta:
        model = ToolFunction

    name = factory.Sequence(lambda n: f"tool_function_{n}")
    arguments = factory.LazyFunction(lambda: '{"param": "value"}')


class ToolCallFactory(factory.Factory):
    class Meta:
        model = ToolCall

    id = factory.LazyFunction(lambda: f"call_{uuid.uuid4().hex[:8]}")
    type = "function"
    function = factory.SubFactory(ToolFunctionFactory)


class OpenRouterInferenceRequestEventFactory(factory.Factory):
    class Meta:
        model = OpenRouterInferenceRequestEvent

    request_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    reply_to_service_event = "ai_chat_response_received"
    model_name = "openai/gpt-4o-mini"
    messages_payload = factory.LazyFunction(lambda: [
        {"role": "user", "content": "Test message"}
    ])
    tools = factory.LazyFunction(lambda: [])
    tool_choice = "auto"
    original_request_payload = factory.LazyFunction(lambda: {
        "room_id": "!test:matrix.example.com",
        "turn_request_id": str(uuid.uuid4())
    })


class AIInferenceResponseEventFactory(factory.Factory):
    class Meta:
        model = AIInferenceResponseEvent

    request_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    original_request_payload = factory.LazyFunction(lambda: {
        "room_id": "!test:matrix.example.com",
        "turn_request_id": str(uuid.uuid4())
    })
    success = True
    text_response = Faker('text', max_nb_chars=100)
    tool_calls = None
    error_message = None
    response_topic = "ai_chat_response_received"


class ExecuteToolRequestFactory(factory.Factory):
    class Meta:
        model = ExecuteToolRequest

    room_id = factory.Sequence(lambda n: f"!room{n}:matrix.example.com")
    tool_call = factory.SubFactory(ToolCallFactory)
    conversation_history_snapshot = factory.LazyFunction(lambda: [])
    last_user_event_id = factory.Sequence(lambda n: f"$event{n}:matrix.example.com")
    original_request_payload = factory.LazyFunction(lambda: {
        "original_ai_request_event_id": str(uuid.uuid4())
    })


class ToolExecutionResponseFactory(factory.Factory):
    class Meta:
        model = ToolExecutionResponse

    original_tool_call_id = factory.LazyFunction(lambda: f"call_{uuid.uuid4().hex[:8]}")
    tool_name = factory.Sequence(lambda n: f"test_tool_{n}")
    status = "success"
    result_for_llm_history = Faker('text', max_nb_chars=100)
    commands_to_publish = factory.LazyFunction(lambda: [])
    original_request_payload = factory.LazyFunction(lambda: {
        "original_ai_request_event_id": str(uuid.uuid4())
    })


class SendMatrixMessageCommandFactory(factory.Factory):
    class Meta:
        model = SendMatrixMessageCommand

    room_id = factory.Sequence(lambda n: f"!room{n}:matrix.example.com")
    text = Faker('text', max_nb_chars=200)


class ActivateListeningEventFactory(factory.Factory):
    class Meta:
        model = ActivateListeningEvent

    room_id = factory.Sequence(lambda n: f"!room{n}:matrix.example.com")
    activation_message_event_id = factory.Sequence(lambda n: f"$event{n}:matrix.example.com")
    triggering_sender_display_name = Faker('name')
    triggering_message_body = Faker('text', max_nb_chars=100)


class BotDisplayNameReadyEventFactory(factory.Factory):
    class Meta:
        model = BotDisplayNameReadyEvent

    display_name = Faker('first_name')
    user_id = factory.Sequence(lambda n: f"@bot{n}:matrix.example.com")


class HistoricalMessageFactory(factory.Factory):
    class Meta:
        model = HistoricalMessage

    role = "user"
    name = Faker('name')
    content = Faker('text', max_nb_chars=100)
    event_id = factory.Sequence(lambda n: f"$event{n}:matrix.example.com")
    timestamp = factory.LazyFunction(lambda: datetime.now(timezone.utc).timestamp())


class BatchedUserMessageFactory(factory.Factory):
    class Meta:
        model = BatchedUserMessage

    name = Faker('name')
    content = Faker('text', max_nb_chars=100)
    event_id = factory.Sequence(lambda n: f"$event{n}:matrix.example.com")