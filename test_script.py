#!/usr/bin/env python3
"""
OmniLogic API Test Script

This script provides a simple command-line interface to test authentication and telemetry
retrieval from the Hayward OmniLogic API. Results are saved to a timestamped file in the
test_data directory for review.
"""

import os
import json
import asyncio
import logging
import getpass
from datetime import datetime
from omnilogic import OmniLogic

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
_LOGGER = logging.getLogger(__name__)

# Ensure test_data directory exists
TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), "test_data")
os.makedirs(TEST_DATA_DIR, exist_ok=True)

async def run_test():
    """Run authentication and telemetry test"""
    print("\n=== OmniLogic API Test Script ===\n")
    
    # Get credentials
    email = input("Enter your OmniLogic email: ")
    password = getpass.getpass("Enter your OmniLogic password: ")
    
    # Initialize client
    client = OmniLogic(email, password)
    
    # Test authentication
    print("\nTesting authentication...")
    try:
        token, userid = await client.connect()
        print(f"✓ Authentication successful!")
        print(f"  User ID: {userid}")
        print(f"  Token: {token[:10]}...{token[-10:] if token and len(token) > 20 else ''}")
    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        await client.close()
        return
    
    # Test telemetry retrieval
    print("\nRetrieving telemetry data...")
    try:
        telemetry = await client.get_telemetry_data()
        print(f"✓ Telemetry data retrieved successfully!")
        
        # Save results to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(TEST_DATA_DIR, f"telemetry_{timestamp}.json")
        
        with open(filename, 'w') as f:
            json.dump(telemetry, f, indent=2)
        
        print(f"\nResults saved to: {filename}")
        
        # Display summary of telemetry data
        if telemetry and isinstance(telemetry, dict):
            print("\nTelemetry Summary:")
            
            # Count systems and devices
            system_count = len(telemetry.get("systems", []))
            print(f"  Systems: {system_count}")
            
            # Show first system details if available
            if system_count > 0:
                system = telemetry["systems"][0]
                print(f"  First System Name: {system.get('systemName', 'Unknown')}")
                print(f"  First System ID: {system.get('systemId', 'Unknown')}")
                
                # Count bodies of water
                bows = system.get("bows", [])
                print(f"  Bodies of Water: {len(bows)}")
                
                # Show equipment counts
                if bows:
                    equipment = bows[0].get("equipment", [])
                    print(f"  Equipment in first BOW: {len(equipment)}")
        
    except Exception as e:
        print(f"✗ Telemetry retrieval failed: {e}")
    
    # Close the client session
    await client.close()
    
    print("\nTest completed.")

if __name__ == "__main__":
    asyncio.run(run_test())
