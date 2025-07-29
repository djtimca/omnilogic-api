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
    
    # Get telemetry data
    print("\nTesting telemetry retrieval...")
    telemetry = await client.get_telemetry_data()
    if telemetry:
        print("✓ Telemetry data retrieved successfully!")
        
        # Save telemetry to file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        telemetry_file = os.path.join(TEST_DATA_DIR, f"telemetry_{timestamp}.json")
        with open(telemetry_file, 'w') as f:
            json.dump(telemetry, f, indent=2)
        print(f"\nResults saved to: {os.path.abspath(telemetry_file)}")
        
        # Save fresh MSP config file with timestamp
        if hasattr(client, 'msp_config') and client.msp_config:
            msp_config_file = os.path.join(TEST_DATA_DIR, f"MspConfiguration_{timestamp}.xml")
            with open(msp_config_file, 'w') as f:
                f.write(client.msp_config)
            print(f"MSP config saved to: {os.path.abspath(msp_config_file)}")
        
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
    else:
        print("✗ Failed to retrieve telemetry data")
    
    # Test set_chlor_params method - now uses MSP config defaults with override capability
    print("\nTesting set_chlor_params method...")
    poolId = 1
    chlorId = 5  # Use chlorinator ID from MSP config (System-Id=6)
    
    print(f"  Calling set_chlor_params with MSP config defaults (only overriding cfgState to enable)")
    print(f"  This will parse current config from MSP and use those values, overriding cfgState=3 (enable)")
    
    try:
        # Test: Override specific parameters
        print(f"\n  Testing with specific parameter overrides...")
        success2, response2 = await client.set_chlor_params(
            poolId=poolId, 
            chlorId=chlorId,
            cfgState=3,      # Enable
            opMode=1,        # Timed mode
            timedPercent=40  # 40% override
        )
        if success2:
            print("✓ set_chlor_params call successful with parameter overrides!")
        else:
            print("✗ set_chlor_params call with overrides failed")
            print(f"  Full response: {response2}")
            
    except Exception as e:
        print(f"✗ set_chlor_params test failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Close the client session
    await client.close()
    
    print("\nTest completed.")

if __name__ == "__main__":
    asyncio.run(run_test())
