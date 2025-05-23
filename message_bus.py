import asyncio
import logging
from collections import defaultdict
from typing import Callable, Any, Dict, List

from event_definitions import BaseEvent, EventType

logger = logging.getLogger(__name__)

class MessageBus:
    def __init__(self):
        """Initializes the message bus with topic queues and subscriber tasks."""
        self.topics: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self.subscriber_tasks: List[asyncio.Task] = []
        self._stop_event = asyncio.Event()
        logger.info("MessageBus initialized.")

    async def publish(self, event: BaseEvent) -> None:
        """Publishes an event to all subscribers of its event_type."""
        event_key = event.event_type.value if isinstance(event.event_type, EventType) else str(event.event_type)
        if not self.topics[event_key]:
            logger.debug(f"No subscribers for event type '{event_key}'.")
            return
        for queue in self.topics[event_key]:
            await queue.put(event)

    def subscribe(self, event_type: EventType | str, callback: Callable[[BaseEvent], Any]) -> None:
        """Subscribes a callback to an event type. The callback runs in its own task."""
        event_key = event_type.value if isinstance(event_type, EventType) else str(event_type)
        queue = asyncio.Queue()
        self.topics[event_key].append(queue)
        async def listener():
            while not self._stop_event.is_set():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    if event:
                        await callback(event)
                        queue.task_done()
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error in listener for '{event_type}' with callback {callback.__name__}: {e}")
        task = asyncio.create_task(listener())
        self.subscriber_tasks.append(task)
        logger.debug(f"Subscribed {callback.__name__} to '{event_type}'. Task: {task.get_name()}")

    async def shutdown(self) -> None:
        """Signals all listeners to stop and waits for them to finish."""
        logger.info("Bus: Shutdown initiated.")
        self._stop_event.set()
        if self.subscriber_tasks:
            logger.info(f"Bus: Waiting for {len(self.subscriber_tasks)} listener tasks to complete...")
            await asyncio.gather(*self.subscriber_tasks, return_exceptions=True)
        logger.info("Bus: All listener tasks completed. MessageBus shutdown complete.")