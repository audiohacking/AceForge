#!/usr/bin/env python3
"""
Test SSL context manager for model downloads.
"""

import sys
import ssl
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_ssl_context_manager():
    """Test the SSL context manager."""
    print("=" * 60)
    print("Test: SSL Context Manager")
    print("=" * 60)
    
    # Import the context manager
    from cdmf_stem_splitting import _SSLContextManager
    
    # Save original context
    original = ssl._create_default_https_context
    print(f"Original SSL context: {original}")
    
    # Test context manager
    print("\nEntering SSL context manager...")
    with _SSLContextManager():
        current = ssl._create_default_https_context
        print(f"Current SSL context: {current}")
        
        # Verify that the context was changed to unverified context
        unverified = ssl._create_unverified_context
        if current == unverified:
            print("✓ SSL context changed to unverified context successfully")
        elif current != original:
            print("✓ SSL context changed (but not to expected unverified context)")
        else:
            print("✗ SSL context was not changed")
            return False
    
    # Verify restoration
    restored = ssl._create_default_https_context
    print(f"\nRestored SSL context: {restored}")
    
    if restored == original:
        print("✓ SSL context restored successfully to original")
        return True
    else:
        print("✗ SSL context was not restored to original")
        return False


def main():
    """Run the test."""
    try:
        result = test_ssl_context_manager()
        if result:
            print("\n✓ Test passed!")
            sys.exit(0)
        else:
            print("\n✗ Test failed")
            sys.exit(1)
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
