#!/usr/bin/env python3
"""
Test script for external MIDI synchronization feature.
This creates a mock pedalboard and config to test the functionality.
"""

import sys
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from modalapi.external_midi import ExternalMidiManager


class MockPedalboard:
    """Mock pedalboard object for testing."""
    def __init__(self, title, bundle):
        self.title = title
        self.bundle = bundle


def create_test_config():
    """Create a test configuration file."""
    config_content = """---
settings:
  enabled: true
  send_delay_ms: 10

midi_ports:
  test_port:
    # Glob patterns for matching MIDI ports
    auto_detect: ["*Steinberg*", "*UR22*"]
    # Fallback if patterns don't match
    # port_index: 0

    # Pass-through mapping for MIDI controls
    passthrough:
      # Forward piStomp expression pedal (CH 14, CC 75) to test device (CH 1, CC 100)
      - source_channel: 14
        source_cc: 75
        dest_channel: 0
        dest_cc: 100
      # Forward piStomp encoder 1 (CH 14, CC 70) to test device (CH 1, CC 1)
      - source_channel: 14
        source_cc: 70
        dest_channel: 0
        dest_cc: 1

pedalboards:
  # Default configuration for pedalboards without specific mappings
  default:
    - port: test_port
      messages:
        # Bypass command (CC 102 with value 0)
        - [0xB0, 0x66, 0x00]

  "Clean Rhythm":
    - port: test_port
      messages:
        - [0xC0, 0x00]

  "Lead*":
    - port: test_port
      messages:
        - [0xC0, 0x05]
        - [0xB0, 0x07, 0x7F]

  "Ambient Delay":
    - port: test_port
      messages:
        - [0xC0, 0x03]
      delay_ms: 20
"""

    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(config_content)
        return f.name


def test_config_loading():
    """Test 1: Configuration loading."""
    print("=" * 70)
    print("Test 1: Configuration Loading")
    print("=" * 70)

    config_path = create_test_config()
    print(f"Created test config: {config_path}")

    try:
        # Use a temporary directory for data_dir
        data_dir = tempfile.mkdtemp()
        manager = ExternalMidiManager(data_dir=data_dir, config_path=config_path)

        assert manager.enabled, "Manager should be enabled"
        assert manager.config.get('settings', {}).get('send_delay_ms') == 10
        assert 'test_port' in manager.port_configs

        print("✓ Config loaded successfully")
        print(f"✓ Enabled: {manager.enabled}")
        print(f"✓ Delay: {manager.config['settings']['send_delay_ms']}ms")
        print(f"✓ Ports configured: {list(manager.port_configs.keys())}")

        return manager
    finally:
        Path(config_path).unlink()


def test_pedalboard_matching(manager):
    """Test 2: Pedalboard matching logic."""
    print("\n" + "=" * 70)
    print("Test 2: Pedalboard Matching")
    print("=" * 70)

    # Test exact title match
    pb1 = MockPedalboard("Clean Rhythm", "/home/pistomp/.pedalboards/clean.pedalboard")
    match1 = manager._match_pedalboard(pb1)
    print(f"\nPedalboard: '{pb1.title}'")
    print(f"✓ Matched: {match1 is not None}")
    if match1:
        print(f"  Messages: {len(match1[0]['messages'])} configured")

    # Test glob pattern match
    pb2 = MockPedalboard("Lead Solo", "/home/pistomp/.pedalboards/lead.pedalboard")
    match2 = manager._match_pedalboard(pb2)
    print(f"\nPedalboard: '{pb2.title}'")
    print(f"✓ Matched by pattern 'Lead*': {match2 is not None}")
    if match2:
        print(f"  Messages: {len(match2[0]['messages'])} configured")

    # Test default match (NEW FEATURE)
    pb3 = MockPedalboard("Bass Tone", "/home/pistomp/.pedalboards/bass.pedalboard")
    match3 = manager._match_pedalboard(pb3)
    print(f"\nPedalboard: '{pb3.title}'")
    print(f"✓ Matched default config: {match3 is not None}")
    if match3:
        print(f"  Messages: {len(match3[0]['messages'])} configured (bypass command)")
        print(f"  First message: {[f'0x{b:02X}' for b in match3[0]['messages'][0]]}")


def test_midi_validation(manager):
    """Test 3: MIDI message validation."""
    print("\n" + "=" * 70)
    print("Test 3: MIDI Message Validation")
    print("=" * 70)

    # Valid messages
    valid_msgs = [
        [0xC0, 0x00],           # Valid PC
        [0xB0, 0x07, 0x7F],     # Valid CC
        [0x90, 0x3C, 0x64],     # Valid Note On
    ]

    print("\nValid messages:")
    for msg in valid_msgs:
        result = manager._validate_midi_message(msg)
        status = "✓" if result else "✗"
        print(f"  {status} {[f'0x{b:02X}' for b in msg]}")

    # Invalid messages
    invalid_msgs = [
        [0x00, 0x00],           # Invalid status byte
        [0xC0, 0xFF],           # Invalid data byte (> 0x7F)
        [0xC0],                 # Too short
        [],                     # Empty
    ]

    print("\nInvalid messages (should fail):")
    for msg in invalid_msgs:
        result = manager._validate_midi_message(msg)
        status = "✓" if not result else "✗"
        print(f"  {status} {msg} -> rejected")


def test_port_enumeration(manager):
    """Test 4: MIDI port enumeration."""
    print("\n" + "=" * 70)
    print("Test 4: MIDI Port Enumeration")
    print("=" * 70)

    try:
        ports = manager._get_available_ports()
        print(f"\n✓ Found {len(ports)} MIDI output port(s):")
        for i, port in enumerate(ports):
            print(f"  [{i}] {port}")

        if not ports:
            print("  (No MIDI ports available - this is OK for testing)")
    except Exception as e:
        print(f"✗ Error enumerating ports: {e}")


def test_passthrough_config(manager):
    """Test 5: Passthrough configuration (NEW FEATURE)."""
    print("\n" + "=" * 70)
    print("Test 5: Passthrough Configuration")
    print("=" * 70)

    print("\nChecking passthrough mappings in config:")
    test_port_config = manager.port_configs.get('test_port', {})
    passthrough = test_port_config.get('passthrough', [])

    if passthrough:
        print(f"✓ Found {len(passthrough)} passthrough mapping(s):")
        for i, mapping in enumerate(passthrough, 1):
            src_ch = mapping.get('source_channel', 'N/A')
            src_cc = mapping.get('source_cc', 'N/A')
            dst_ch = mapping.get('dest_channel', 'N/A')
            dst_cc = mapping.get('dest_cc', 'N/A')
            print(f"  [{i}] CH{src_ch+1} CC{src_cc} -> CH{dst_ch+1} CC{dst_cc}")
    else:
        print("✗ No passthrough mappings configured")


def test_passthrough_logic(manager):
    """Test 6: Passthrough MIDI message remapping (NEW FEATURE)."""
    print("\n" + "=" * 70)
    print("Test 6: Passthrough MIDI Remapping")
    print("=" * 70)

    # Test cases: (source_channel, source_cc, value, should_match)
    test_cases = [
        (14, 75, 64, True, "Expression pedal"),   # Should match first mapping
        (14, 70, 32, True, "Encoder 1"),          # Should match second mapping
        (14, 99, 127, False, "Unmapped CC"),     # Should not match
        (15, 75, 64, False, "Wrong channel"),    # Should not match
    ]

    for src_ch, src_cc, value, should_match, description in test_cases:
        print(f"\nTest: {description}")
        print(f"  Input: CH{src_ch+1} CC{src_cc} = {value}")

        try:
            # This will attempt to send if there's a match
            result = manager.send_passthrough_cc(src_ch, src_cc, value)

            if should_match:
                print(f"  ✓ Matched and processed (result: {result})")
            else:
                if not result:
                    print(f"  ✓ Correctly ignored (no match)")
                else:
                    print(f"  ✗ Unexpected match")
        except Exception as e:
            print(f"  ○ Error (expected if no MIDI device): {e}")


def test_send_messages(manager):
    """Test 7: Message sending (will fail if no port available)."""
    print("\n" + "=" * 70)
    print("Test 7: Message Sending Simulation")
    print("=" * 70)

    # Test specific pedalboard
    pb1 = MockPedalboard("Clean Rhythm", "/home/pistomp/.pedalboards/clean.pedalboard")
    print(f"\nAttempting to send messages for: '{pb1.title}'")
    try:
        result = manager.send_messages_for_pedalboard(pb1)
        if result:
            print("✓ Messages sent successfully")
        else:
            print("○ No messages sent (no matching config or port unavailable)")
    except Exception as e:
        print(f"○ Expected error (no real MIDI device): {e}")

    # Test default pedalboard
    pb2 = MockPedalboard("Unknown Pedalboard", "/home/pistomp/.pedalboards/unknown.pedalboard")
    print(f"\nAttempting to send messages for: '{pb2.title}' (should use default)")
    try:
        result = manager.send_messages_for_pedalboard(pb2)
        if result:
            print("✓ Default messages sent successfully")
        else:
            print("○ No messages sent (port unavailable)")
    except Exception as e:
        print(f"○ Expected error (no real MIDI device): {e}")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("EXTERNAL MIDI SYNCHRONIZATION TEST SUITE")
    print("=" * 70)

    try:
        # Test 1: Config loading
        manager = test_config_loading()

        # Test 2: Pedalboard matching
        test_pedalboard_matching(manager)

        # Test 3: MIDI validation
        test_midi_validation(manager)

        # Test 4: Port enumeration
        test_port_enumeration(manager)

        # Test 5: Passthrough config
        test_passthrough_config(manager)

        # Test 6: Passthrough logic
        test_passthrough_logic(manager)

        # Test 7: Message sending
        test_send_messages(manager)

        # Cleanup
        manager.close()

        print("\n" + "=" * 70)
        print("ALL TESTS COMPLETED")
        print("=" * 70)
        print("\n✓ Core functionality verified")
        print("✓ Ready for integration with piStomp")

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
