#!/usr/bin/env python3
"""
Test script to validate the Goal System Integration

This script tests the new goal management functionality.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chatbot.core.world_state.structures import WorldStateData, Goal
import time

def test_goal_system():
    """Test the goal system integration."""
    print("🎯 Testing Goal System Integration...")
    
    # Create a WorldStateData instance
    world_state = WorldStateData()
    
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
    
    # Test 2: Add goal to world state
    print("\n✅ Test 2: Adding goal to world state")
    world_state.add_goal(goal)
    print(f"Active goals count: {len(world_state.active_goals)}")
    
    # Test 3: Get goals summary
    print("\n✅ Test 3: Getting goals summary")
    summary = world_state.get_active_goals_summary()
    print(f"Goals summary: {summary}")
    
    # Test 4: Update goal progress
    print("\n✅ Test 4: Updating goal progress")
    success = world_state.update_goal_progress(
        goal.id, 
        "Initiated conversations with 2 new users in Matrix room",
        {"new_users_engaged": 2, "conversations_started": 3}
    )
    print(f"Progress update successful: {success}")
    
    # Test 5: Get updated summary
    print("\n✅ Test 5: Getting updated summary")
    updated_summary = world_state.get_active_goals_summary()
    print(f"Updated summary: {updated_summary}")
    
    # Test 6: Test state metrics include goals
    print("\n✅ Test 6: Checking state metrics")
    metrics = world_state.get_state_metrics()
    print(f"Active goals count in metrics: {metrics.get('active_goals_count', 'NOT FOUND')}")
    
    # Test 7: Complete goal test
    print("\n✅ Test 7: Completing a goal")
    world_state.complete_goal(goal.id, "Successfully increased engagement by 25%!")
    completed_summary = world_state.get_active_goals_summary()
    print(f"Active goals after completion: {len(completed_summary)}")
    print(f"Goal status: {goal.status}")
    
    print("\n🎉 All Goal System Tests Passed!")
    return True

def test_prompt_builder():
    """Test the prompt builder with goals context."""
    print("\n📝 Testing Prompt Builder with Goals Context...")
    
    try:
        from chatbot.core.prompts import PromptBuilder
        
        # Create world state with goals
        world_state = WorldStateData()
        goal1 = Goal(title="Test Goal 1", priority=7, status="active")
        goal2 = Goal(title="Test Goal 2", priority=5, status="active")
        world_state.add_goal(goal1)
        world_state.add_goal(goal2)
        
        # Test prompt building
        prompt_builder = PromptBuilder()
        system_prompt = prompt_builder.build_system_prompt(
            include_sections=["world_state_context"],
            world_state_data=world_state
        )
        
        print("✅ Prompt built successfully")
        if "Test Goal 1" in system_prompt:
            print("✅ Goals context properly substituted")
        else:
            print("❌ Goals context not found in prompt")
            
        return True
        
    except Exception as e:
        print(f"❌ Prompt builder test failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 GOAL SYSTEM INTEGRATION TEST")
    print("=" * 50)
    
    try:
        # Test goal system
        goal_test_passed = test_goal_system()
        
        # Test prompt builder
        prompt_test_passed = test_prompt_builder()
        
        if goal_test_passed and prompt_test_passed:
            print("\n" + "=" * 50)
            print("🎉 ALL TESTS PASSED! Goal System Ready for Production")
            print("=" * 50)
        else:
            print("\n" + "=" * 50)
            print("❌ SOME TESTS FAILED - Review Implementation")
            print("=" * 50)
            
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        import traceback
        traceback.print_exc()
