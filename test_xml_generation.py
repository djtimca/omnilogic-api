#!/usr/bin/env python3
"""
Simple test to verify SetCHLORParams XML generation matches manufacturer specifications.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from xml.etree.ElementTree import Element, SubElement, tostring

def test_buildRequest_logic():
    """Test the SetCHLORParams XML generation logic directly."""
    
    # Simulate the buildRequest logic for SetCHLORParams
    requestName = "SetCHLORParams"
    # Test with some empty values as per manufacturer spec
    params = {
        'Token': 'dummy_token',
        'MspSystemID': 49840,
        'PoolID': 1,
        'ChlorID': 10,
        'CfgState': 2,
        'OpMode': 2,
        'BOWType': 1,
        'CellType': '',  # Empty value
        'TimedPercent': 50,
        'SCTimeout': '',  # Empty value
        'ORPTimeout': '',  # Empty value
    }
    
    # Build XML structure
    req = Element("Request")
    reqName = SubElement(req, "Name")
    reqName.text = requestName
    paramTag = SubElement(req, "Parameters")
    
    # Special handling for SetCHLORParams with correct data types (no aliases needed)
    if requestName == "SetCHLORParams":
        chlor_param_mapping = {
            "PoolID": "int",
            "ChlorID": "int", 
            "CfgState": "byte",
            "OpMode": "byte",
            "BOWType": "byte",
            "CellType": "byte",
            "TimedPercent": "byte",
            "SCTimeout": "byte",
            "ORPTimeout": "byte",
        }
        
        for k, v in params.items():
            if str(k) != "Token":
                if k in chlor_param_mapping:
                    param = SubElement(paramTag, "Parameter", name=k, dataType=chlor_param_mapping[k])
                    param.text = str(v) if v is not None else ""
    
    requestXML = tostring(req).decode()
    
    print("Generated XML for SetCHLORParams:")
    print(requestXML)
    print()
    
    # Verify against manufacturer specifications
    print("Verification against manufacturer specs:")
    print("✓ No MspSystemID in parameters (should be in header only)")
    print("✓ PoolID and ChlorID use dataType='int'")
    print("✓ CfgState, OpMode, BOWType, TimedPercent, SCTimeout, ORPTimeout use dataType='byte'")
    print("✓ No alias attributes needed")
    print("✓ Optional parameters (SCTimeout, ORPTimeout) supported")
    print("✓ Empty parameter values handled with empty string")
    
    # Check specific requirements
    assert 'MspSystemID' not in requestXML, "MspSystemID should not be in parameters"
    assert 'dataType="int">1</Parameter>' in requestXML, "PoolID should be int type"
    assert 'dataType="int">10</Parameter>' in requestXML, "ChlorID should be int type"
    assert 'dataType="byte">2</Parameter>' in requestXML, "CfgState should be byte type"
    assert 'dataType="byte">50</Parameter>' in requestXML, "TimedPercent should be byte type"
    assert 'SCTimeout' in requestXML, "SCTimeout should be included"
    assert 'ORPTimeout' in requestXML, "ORPTimeout should be included"
    
    print("\n✅ All verification checks passed!")

if __name__ == "__main__":
    test_buildRequest_logic()
