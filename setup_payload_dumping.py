#!/usr/bin/env python3
"""
Script to enable payload dumping and test the functionality.
"""

import os
import json
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def enable_payload_dumping():
    """Enable payload dumping by updating the environment file."""
    env_file = Path("/workspaces/matrixbot/.env")
    
    if not env_file.exists():
        logger.error("❌ .env file not found!")
        return False
    
    # Read current .env content
    with open(env_file, 'r') as f:
        lines = f.readlines()
    
    # Update the payload dumping setting
    updated = False
    for i, line in enumerate(lines):
        if line.startswith("AI_DUMP_PAYLOADS_TO_FILE="):
            lines[i] = "AI_DUMP_PAYLOADS_TO_FILE=true\n"
            updated = True
            break
    
    if not updated:
        # Add the setting if it doesn't exist
        lines.append("AI_DUMP_PAYLOADS_TO_FILE=true\n")
    
    # Write back to .env
    with open(env_file, 'w') as f:
        f.writelines(lines)
    
    logger.info("✅ Payload dumping enabled in .env file")
    return True

def create_test_payload():
    """Create a test payload to verify the dumping functionality."""
    try:
        from chatbot.core.ai_engine import AIDecisionEngine, OptimizationLevel
        
        # Create a test AI engine
        ai_engine = AIDecisionEngine(api_key="test_key", model="test_model", optimization_level=OptimizationLevel.BALANCED)
        
        # Create a sample payload
        test_payload = {
            "model": "test_model",
            "messages": [
                {"role": "system", "content": "Test system prompt"},
                {"role": "user", "content": "Test user prompt with some data"}
            ],
            "temperature": 0.7,
            "max_tokens": 3500
        }
        
        # Test the dumping function
        ai_engine._dump_payload_to_file(test_payload, "test_cycle_001")
        
        logger.info("✅ Test payload dump completed")
        
        # Check if file was created
        dump_dir = Path("data/payload_dumps")
        payload_files = list(dump_dir.glob("payload_*_test_cycle_001.json"))
        
        if payload_files:
            logger.info(f"✅ Found dumped payload file: {payload_files[0]}")
            
            # Read and verify the file
            with open(payload_files[0], 'r') as f:
                dump_data = json.load(f)
            
            logger.info(f"📊 Dumped payload metadata:")
            for key, value in dump_data["metadata"].items():
                logger.info(f"   {key}: {value}")
                
            return True
        else:
            logger.error("❌ No payload dump file found")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error testing payload dump: {e}")
        import traceback
        traceback.print_exc()
        return False

def list_payload_dumps():
    """List existing payload dump files."""
    dump_dir = Path("data/payload_dumps")
    
    if not dump_dir.exists():
        logger.info("📁 Payload dump directory doesn't exist yet")
        return
    
    payload_files = sorted(dump_dir.glob("payload_*.json"))
    
    logger.info(f"📁 Found {len(payload_files)} payload dump files:")
    
    for i, filepath in enumerate(payload_files[-10:], 1):  # Show last 10
        try:
            # Get file size
            file_size = filepath.stat().st_size
            
            # Try to read metadata
            with open(filepath, 'r') as f:
                data = json.load(f)
                metadata = data.get("metadata", {})
                cycle_id = metadata.get("cycle_id", "unknown")
                timestamp = metadata.get("timestamp", "unknown")
                payload_size_kb = metadata.get("payload_size_kb", 0)
            
            logger.info(f"{i:2d}. {filepath.name}")
            logger.info(f"     Cycle: {cycle_id}, Size: {payload_size_kb:.2f} KB, File: {file_size/1024:.2f} KB")
            logger.info(f"     Time: {timestamp}")
            
        except Exception as e:
            logger.warning(f"     Error reading {filepath.name}: {e}")

def main():
    """Main function to set up and test payload dumping."""
    logger.info("🚀 Setting up payload dumping...")
    
    # Enable payload dumping
    if enable_payload_dumping():
        logger.info("✅ Payload dumping enabled")
    else:
        logger.error("❌ Failed to enable payload dumping")
        return
    
    # Create dump directory
    dump_dir = Path("data/payload_dumps")
    dump_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"📁 Dump directory created: {dump_dir.absolute()}")
    
    # Test payload dumping
    logger.info("🧪 Testing payload dumping...")
    if create_test_payload():
        logger.info("✅ Payload dumping test successful")
    else:
        logger.error("❌ Payload dumping test failed")
    
    # List existing dumps
    logger.info("📋 Listing payload dumps...")
    list_payload_dumps()
    
    # Instructions
    logger.info("\n" + "="*60)
    logger.info("📖 PAYLOAD DUMPING INSTRUCTIONS:")
    logger.info("="*60)
    logger.info("1. Payload dumping is now enabled")
    logger.info("2. Live payloads will be saved to: data/payload_dumps/")
    logger.info("3. Each file contains:")
    logger.info("   - metadata (cycle_id, timestamp, size info)")
    logger.info("   - full payload sent to OpenRouter")
    logger.info("4. Files are automatically cleaned up (max 50 files)")
    logger.info("5. To disable: Set AI_DUMP_PAYLOADS_TO_FILE=false in .env")
    logger.info("6. To analyze dumps, use the analyze_payload_dump.py script")

if __name__ == "__main__":
    main()
