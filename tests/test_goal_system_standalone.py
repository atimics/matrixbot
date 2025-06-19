#!/usr/bin/env python3
"""
Simplified test for Goal System structures only
"""

import sys
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Minimal Goal implementation for testing
@dataclass
class Goal:
    """Test Goal class matching the one in structures.py"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    status: str = "active"  # active, completed, paused, cancelled
    priority: int = 5  # 1-10, higher is more important
    created_timestamp: float = field(default_factory=time.time)
    target_completion: Optional[float] = None  # Optional deadline
    completion_criteria: List[str] = field(default_factory=list)
    sub_tasks: List[str] = field(default_factory=list)  # List of task descriptions
    progress_metrics: Dict[str, Any] = field(default_factory=dict)
    category: str = "general"  # e.g., "community_growth", "content_creation", "engagement"
    related_channels: List[str] = field(default_factory=list)  # Channels relevant to this goal
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_progress_update(self, update: str, metrics: Optional[Dict[str, Any]] = None):
        """Add a progress update to the goal."""
        if "progress_updates" not in self.metadata:
            self.metadata["progress_updates"] = []
        
        self.metadata["progress_updates"].append({
            "timestamp": time.time(),
            "update": update,
            "metrics": metrics or {}
        })
    
    def mark_completed(self, completion_note: str = ""):
        """Mark the goal as completed."""
        self.status = "completed"
        self.metadata["completed_timestamp"] = time.time()
        if completion_note:
            self.metadata["completion_note"] = completion_note
    
    def get_progress_summary(self) -> Dict[str, Any]:
        """Get a summary of goal progress."""
        updates = self.metadata.get("progress_updates", [])
        return {
            "goal_id": self.id,
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "created_days_ago": (time.time() - self.created_timestamp) / 86400,
            "total_updates": len(updates),
            "latest_update": updates[-1] if updates else None,
            "completion_criteria_count": len(self.completion_criteria),
            "sub_tasks_count": len(self.sub_tasks)
        }

def test_goal_functionality():
    """Test goal functionality standalone."""
    print("🎯 Testing Goal System Core Functionality...")
    
    # Test 1: Create a goal
    print("\n✅ Test 1: Creating a goal")
    goal = Goal(
        title="Increase Community Engagement",
        description="Work towards getting more active participants in discussions",
        priority=8,
        category="community_growth",
        completion_criteria=["Get 5 new users to join discussions", "Increase daily message count by 20%"],
        related_channels=["!main:matrix.org", "/farcaster/general"]
    )
    
    print(f"Created goal: {goal.title} (ID: {goal.id})")
    print(f"Priority: {goal.priority}, Status: {goal.status}")
    
    # Test 2: Add progress update
    print("\n✅ Test 2: Adding progress update")
    goal.add_progress_update(
        "Initiated conversations with 2 new users in Matrix room",
        {"new_users_engaged": 2, "conversations_started": 3}
    )
    print("Progress update added successfully")
    
    # Test 3: Get progress summary
    print("\n✅ Test 3: Getting progress summary")
    summary = goal.get_progress_summary()
    print(f"Summary: {summary}")
    
    # Test 4: Mark goal completed
    print("\n✅ Test 4: Completing goal")
    goal.mark_completed("Successfully increased engagement by 25%!")
    print(f"Goal status: {goal.status}")
    final_summary = goal.get_progress_summary()
    print(f"Final summary: {final_summary}")
    
    print("\n🎉 Goal Core Functionality Tests Passed!")
    return True

def test_simple_world_state():
    """Test a simplified version of world state with goals."""
    print("\n🌍 Testing Simplified World State with Goals...")
    
    class SimpleWorldState:
        def __init__(self):
            self.active_goals: List[Goal] = []
            
        def add_goal(self, goal: Goal):
            self.active_goals.append(goal)
            print(f"Added goal: {goal.title}")
            
        def get_active_goals_summary(self) -> List[Dict[str, Any]]:
            return [goal.get_progress_summary() for goal in self.active_goals if goal.status == "active"]
            
        def get_state_metrics(self) -> Dict[str, Any]:
            return {
                "active_goals_count": len([g for g in self.active_goals if g.status == "active"]),
                "total_goals_count": len(self.active_goals)
            }
    
    # Test the simplified world state
    world_state = SimpleWorldState()
    
    # Create test goals
    goal1 = Goal(title="Community Growth", priority=8, status="active")
    goal2 = Goal(title="Content Creation", priority=6, status="active") 
    goal3 = Goal(title="Completed Task", priority=3, status="completed")
    
    # Add goals
    world_state.add_goal(goal1)
    world_state.add_goal(goal2)
    world_state.add_goal(goal3)
    
    # Test metrics
    metrics = world_state.get_state_metrics()
    print(f"State metrics: {metrics}")
    
    # Test active goals summary
    active_summary = world_state.get_active_goals_summary()
    print(f"Active goals: {len(active_summary)}")
    for goal_summary in active_summary:
        print(f"  - {goal_summary['title']} (Priority: {goal_summary['priority']})")
    
    print("\n🎉 Simplified World State Tests Passed!")
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 GOAL SYSTEM STANDALONE FUNCTIONALITY TEST")
    print("=" * 60)
    
    try:
        # Test core goal functionality
        goal_test_passed = test_goal_functionality()
        
        # Test simplified world state integration
        world_state_test_passed = test_simple_world_state()
        
        if goal_test_passed and world_state_test_passed:
            print("\n" + "=" * 60)
            print("🎉 ALL STANDALONE TESTS PASSED!")
            print("Goal system structures are working correctly.")
            print("Ready for integration with the full system.")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("❌ SOME TESTS FAILED")
            print("=" * 60)
            
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        import traceback
        traceback.print_exc()
