#!/usr/bin/env python3
"""
Live AI Prompt Analysis Tool

This script analyzes the current AI prompt structure in the running system
to understand what's contributing to the ~110KB payload size we see in production.
"""

import asyncio
import json
import logging
import requests
from typing import Dict, Any

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_component_sizes(data: Dict[str, Any], path: str = "") -> Dict[str, int]:
    """Recursively analyze the size of dictionary components."""
    sizes = {}
    
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            
            # Calculate size of this component
            try:
                value_json = json.dumps(value, default=str)
                size_bytes = len(value_json.encode('utf-8'))
                sizes[current_path] = size_bytes
                
                # If it's a large component, analyze sub-components
                if isinstance(value, dict) and size_bytes > 1024:  # > 1KB
                    child_sizes = analyze_component_sizes(value, current_path)
                    sizes.update(child_sizes)
                    
            except Exception as e:
                logger.warning(f"Could not analyze component {current_path}: {e}")
                sizes[current_path] = 0
                
    return sizes

async def get_live_prompt_analysis():
    """Get live prompt analysis from the API."""
    try:
        # Try to get the analysis from our new API endpoint
        response = requests.get("http://localhost:8000/api/ai/prompt/analysis", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            logger.debug("✅ Successfully got live prompt analysis from API")
            return data
        else:
            logger.error(f"❌ API returned {response.status_code}: {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        logger.error("❌ Could not connect to API server on localhost:8000")
        return None
    except Exception as e:
        logger.error(f"❌ Error getting live analysis: {e}")
        return None

def analyze_system_logs():
    """Analyze recent system logs for payload information."""
    logger.debug("📋 Analyzing recent system logs for payload size patterns...")
    
    try:
        # Try to read recent logs if available
        with open("/workspaces/matrixbot/chatbot.log", "r") as f:
            lines = f.readlines()
            
        # Look for recent AI payload logs
        payload_logs = []
        for line in lines[-1000:]:  # Last 1000 lines
            if "Sending payload of size" in line:
                payload_logs.append(line.strip())
                
        if payload_logs:
            logger.debug(f"📊 Found {len(payload_logs)} recent payload size logs:")
            for log in payload_logs[-10:]:  # Show last 10
                logger.debug(f"  {log}")
        else:
            logger.debug("No recent payload size logs found")
            
    except FileNotFoundError:
        logger.debug("No chatbot.log file found")
    except Exception as e:
        logger.warning(f"Error reading logs: {e}")

def main():
    """Main analysis function."""
    logger.debug("🔍 Starting Live AI Prompt Analysis")
    logger.debug("=" * 60)
    
    # Get live analysis from API
    api_analysis = asyncio.run(get_live_prompt_analysis())
    
    if api_analysis:
        logger.debug("\n📊 LIVE PAYLOAD ANALYSIS:")
        logger.debug("=" * 40)
        
        analysis = api_analysis.get("analysis", {})
        config = api_analysis.get("configuration", {})
        recommendations = api_analysis.get("recommendations", [])
        
        logger.debug(f"Total payload size: {analysis.get('total_payload_size_kb')} KB")
        logger.debug(f"System prompt size: {analysis.get('system_prompt_size_kb')} KB")
        logger.debug(f"User prompt size: {analysis.get('user_prompt_size_kb')} KB")
        logger.debug(f"Model: {analysis.get('model')}")
        
        logger.debug("\n⚙️  CURRENT CONFIGURATION:")
        logger.debug("=" * 30)
        for key, value in config.items():
            logger.debug(f"{key}: {value}")
            
        if recommendations:
            logger.debug("\n💡 RECOMMENDATIONS:")
            logger.debug("=" * 20)
            for rec in recommendations:
                logger.debug(f"• {rec}")
        
        # Check thresholds
        thresholds = api_analysis.get("payload_thresholds", {})
        current_size = analysis.get('total_payload_size_kb', 0)
        
        logger.debug(f"\n🚦 PAYLOAD SIZE STATUS:")
        logger.debug("=" * 25)
        logger.debug(f"Current: {current_size} KB")
        logger.debug(f"Warning threshold: {thresholds.get('warning_kb')} KB")
        logger.debug(f"Critical threshold: {thresholds.get('critical_kb')} KB")
        logger.debug(f"OpenRouter limit estimate: {thresholds.get('openrouter_limit_estimate_kb')} KB")
        
        if current_size > thresholds.get('critical_kb', 300):
            logger.warning("🔴 CRITICAL: Payload size is very large!")
        elif current_size > thresholds.get('warning_kb', 200):
            logger.warning("🟡 WARNING: Payload size is getting large")
        else:
            logger.debug("🟢 GOOD: Payload size is within acceptable range")
    
    # Analyze system logs
    logger.debug("\n" + "=" * 60)
    analyze_system_logs()
    
    logger.debug("\n✅ Live analysis complete!")

if __name__ == "__main__":
    main()
