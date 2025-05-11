import asyncio
from collections import defaultdict
from typing import Callable, Any, Dict, List

from event_definitions import BaseEvent

class MessageBus:
    def __init__(self):
        self.topics: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self.subscriber_tasks: List[asyncio.Task] = []
        self._stop_event = asyncio.Event()
        print("MessageBus initialized.")

    async def publish(self, event: BaseEvent):
        event_type = event.event_type
        # print(f"Bus: Publishing event type '{event_type}' to {len(self.topics.get(event_type, []))} queues.")
        if not self.topics[event_type]:
            # print(f"Bus: No subscribers for event type '{event_type}'.")
            return
            
        for queue in self.topics[event_type]:
            await queue.put(event)

    def subscribe(self, event_type: str, callback: Callable[[BaseEvent], asyncio.Future]):
        """
        Subscribes a callback to an event type.
        The callback will be run in its own continuously listening task.
        """
        queue = asyncio.Queue()
        self.topics[event_type].append(queue)
        
        async def listener():
            # print(f"Bus: Listener started for event type '{event_type}' with callback {callback.__name__}")
            while not self._stop_event.is_set():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    if event:
                        # print(f"Bus: Listener for '{event_type}' got event, calling {callback.__name__}")
                        await callback(event)
                        queue.task_done()
                except asyncio.TimeoutError:
                    continue # Allows checking _stop_event
                except Exception as e:
                    print(f"Bus: Error in listener for '{event_type}' with callback {callback.__name__}: {e}")
                    # Potentially re-queue or log to a dead-letter queue in a real system

        task = asyncio.create_task(listener())
        self.subscriber_tasks.append(task)
        # print(f"Bus: Subscribed {callback.__name__} to '{event_type}'. Task: {task.get_name()}")

    async def shutdown(self):
        print("Bus: Shutdown initiated.")
        self._stop_event.set()
        # Wait for listener tasks to finish (they check _stop_event)
        if self.subscriber_tasks:
            print(f"Bus: Waiting for {len(self.subscriber_tasks)} listener tasks to complete...")
            await asyncio.gather(*self.subscriber_tasks, return_exceptions=True)
        print("Bus: All listener tasks completed. MessageBus shutdown complete.")