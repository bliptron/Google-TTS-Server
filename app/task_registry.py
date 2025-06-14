import threading
import logging

logger = logging.getLogger(__name__)

class TaskCancelledError(Exception):
    pass

class TaskRegistry:
    """Registry for tracking and cancelling active TTS tasks."""
    def __init__(self):
        self.tasks = {}
    
    def register(self, task_id):
        """Register a new task with its cancellation event."""
        self.tasks[task_id] = threading.Event()
    
    def cancel(self, task_id):
        """Signal cancellation for a task."""
        if task_id in self.tasks:
            self.tasks[task_id].set()
    
    def is_cancelled(self, task_id):
        """Check if task has been cancelled."""
        return task_id in self.tasks and self.tasks[task_id].is_set()
    
    def unregister(self, task_id):
        """Remove task from registry."""
        if task_id in self.tasks:
            del self.tasks[task_id]

# Global task registry instance
task_registry = TaskRegistry()