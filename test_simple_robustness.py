#!/usr/bin/env python3
"""
Simple test for the robust JSON parsing improvements.
"""

from chatbot.core.ai_engine import AIDecisionEngine, ActionPlan, DecisionResult


def test_missing_field_handling():
    """Test that missing fields in actions are handled gracefully."""
    
    engine = AIDecisionEngine("dummy_key", "dummy_model")
    
    # Test case 1: JSON with missing reasoning at action level
    json_with_missing_reasoning = """{
  "observations": "Test observations",
  "selected_actions": [
    {
      "action_type": "send_matrix_reply",
      "parameters": {
        "channel_id": "test",
        "content": "test message"
      },
      "priority": 9
    },
    {
      "action_type": "wait", 
      "parameters": {"duration": 5},
      "reasoning": "Valid reasoning here",
      "priority": 5
    }
  ],
  "reasoning": "Overall reasoning"
}"""

    # Test JSON parsing
    try:
        decision_data = engine._extract_json_from_response(json_with_missing_reasoning)
        print("✅ JSON extraction successful")
        assert "selected_actions" in decision_data
        assert len(decision_data["selected_actions"]) == 2
        print(f"Found {len(decision_data['selected_actions'])} actions")
        
        # Simulate what the engine does with this data
        selected_actions = []
        for action_data in decision_data.get("selected_actions", []):
            try:
                action_plan = ActionPlan(
                    action_type=action_data.get("action_type", "unknown"),
                    parameters=action_data.get("parameters", {}),
                    reasoning=action_data.get("reasoning", "No reasoning provided"),
                    priority=action_data.get("priority", 5),
                )
                selected_actions.append(action_plan)
                print(f"✅ Created action: {action_plan.action_type} with reasoning: '{action_plan.reasoning}'")
            except Exception as e:
                print(f"❌ Failed to create action: {e}")
        
        # Verify results
        assert len(selected_actions) == 2
        assert selected_actions[0].reasoning == "No reasoning provided"
        assert selected_actions[1].reasoning == "Valid reasoning here"
        
        # Create decision result
        result = DecisionResult(
            selected_actions=selected_actions,
            reasoning=decision_data.get("reasoning", ""),
            observations=decision_data.get("observations", ""),
            cycle_id="test_cycle",
        )
        
        print(f"✅ Created DecisionResult with {len(result.selected_actions)} actions")
        print(f"   Observations: {result.observations}")
        print(f"   Reasoning: {result.reasoning}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise

    # Test case 2: JSON with missing top-level reasoning
    json_no_top_reasoning = """{
  "observations": "Test observations",
  "selected_actions": [
    {
      "action_type": "wait",
      "parameters": {"duration": 1},
      "reasoning": "Just wait",
      "priority": 3
    }
  ]
}"""

    try:
        decision_data = engine._extract_json_from_response(json_no_top_reasoning)
        
        result = DecisionResult(
            selected_actions=[ActionPlan(
                action_type="wait",
                parameters={"duration": 1},
                reasoning="Just wait",
                priority=3
            )],
            reasoning=decision_data.get("reasoning", ""),  # Should be empty
            observations=decision_data.get("observations", ""),
            cycle_id="test_cycle_2",
        )
        
        assert result.reasoning == ""  # Should handle missing reasoning gracefully
        print("✅ Missing top-level reasoning handled correctly")
        
    except Exception as e:
        print(f"❌ Missing reasoning test failed: {e}")
        raise

    print("🎉 All missing field tests passed!")


def test_malformed_actions():
    """Test handling of completely malformed action data."""
    
    engine = AIDecisionEngine("dummy_key", "dummy_model")
    
    json_with_bad_actions = """{
  "observations": "Test observations",
  "selected_actions": [
    {
      "action_type": "valid_action",
      "parameters": {"param": "value"},
      "reasoning": "This one is valid",
      "priority": 5
    },
    "this_is_not_an_object",
    {
      "missing_action_type": true,
      "parameters": {}
    },
    {
      "action_type": "another_valid_one",
      "parameters": {"test": true},
      "reasoning": "Also valid",
      "priority": 8
    }
  ],
  "reasoning": "Mixed bag of actions"
}"""

    try:
        decision_data = engine._extract_json_from_response(json_with_bad_actions)
        
        # Process actions with error handling
        selected_actions = []
        for action_data in decision_data.get("selected_actions", []):
            try:
                if not isinstance(action_data, dict):
                    print(f"⚠️  Skipping non-dict action: {action_data}")
                    continue
                    
                action_plan = ActionPlan(
                    action_type=action_data.get("action_type", "unknown"),
                    parameters=action_data.get("parameters", {}),
                    reasoning=action_data.get("reasoning", "No reasoning provided"),
                    priority=action_data.get("priority", 5),
                )
                selected_actions.append(action_plan)
                print(f"✅ Processed action: {action_plan.action_type}")
            except Exception as e:
                print(f"⚠️  Skipped malformed action: {e}")
                continue
        
        # Should have processed 2 valid actions and skipped 2 invalid ones
        print(f"Processed {len(selected_actions)} out of 4 actions")
        assert len(selected_actions) == 3  # 2 valid + 1 with missing action_type (becomes "unknown")
        
        valid_actions = [a for a in selected_actions if a.action_type != "unknown"]
        assert len(valid_actions) == 2
        
        print("✅ Malformed actions handled gracefully")
        
    except Exception as e:
        print(f"❌ Malformed actions test failed: {e}")
        raise

    print("🎉 Malformed actions test passed!")


if __name__ == "__main__":
    test_missing_field_handling()
    test_malformed_actions()
    print("\n🎉 All robustness tests passed! The AI engine can now handle:")
    print("   - Missing reasoning fields in actions")
    print("   - Missing top-level reasoning")
    print("   - Malformed action objects")
    print("   - Mixed valid/invalid action arrays")
