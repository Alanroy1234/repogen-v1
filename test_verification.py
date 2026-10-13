import sys
import os
import unittest
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backend.tag_utils as tag_utils
from backend.s7_client import S7Client, Snap7Exception
from backend.tag_manager import TagManager
from backend.plc_manager import PLCManager
from backend.database import Database

class TestRepoGenVerification(unittest.TestCase):
    def test_01_snap7_exception_class(self):
        """Verify Snap7Exception is properly imported and evaluated without AttributeError."""
        import snap7
        self.assertFalse(hasattr(snap7, 'exceptions'), "snap7 should not have exceptions attribute in 3.2.1")
        # Verify Snap7Exception can be caught in an except clause
        try:
            raise Snap7Exception("Test error")
        except Snap7Exception as e:
            self.assertEqual(str(e), "Test error")

    def test_02_address_parsing(self):
        """Verify parsing of various address formats."""
        # BOOL
        b, bi = tag_utils.parse_address("0.0", "BOOL")
        self.assertEqual((b, bi), (0, 0))
        b, bi = tag_utils.parse_address("M10.5", "BOOL")
        self.assertEqual((b, bi), (10, 5))
        
        # INT / REAL / DINT
        b, bi = tag_utils.parse_address("MW0", "INT")
        self.assertEqual((b, bi), (0, 0))
        b, bi = tag_utils.parse_address("0", "INT")
        self.assertEqual((b, bi), (0, 0))
        b, bi = tag_utils.parse_address("0.0", "REAL")
        self.assertEqual((b, bi), (0, 0))
        b, bi = tag_utils.parse_address("DB1.DBD4", "REAL")
        self.assertEqual((b, bi), (4, 0))

    def test_03_encoding_and_decoding(self):
        """Verify encode and decode roundtrip for all types."""
        types_and_vals = [
            ("BOOL", True),
            ("BYTE", 200),
            ("SINT", -50),
            ("USINT", 250),
            ("INT", -1234),
            ("UINT", 54321),
            ("WORD", 65535),
            ("DINT", -100000),
            ("UDINT", 2000000),
            ("DWORD", 4000000000),
            ("REAL", 123.456),
        ]
        
        for dt, val in types_and_vals:
            size = tag_utils.get_data_type_size(dt)
            buf = bytearray(size)
            tag_utils.encode_value(val, dt, buf, bit_offset=0)
            decoded = tag_utils.decode_value(buf, dt, bit_offset=0)
            if dt == "REAL":
                self.assertAlmostEqual(decoded, val, places=2)
            else:
                self.assertEqual(decoded, val)

    def test_04_cpu_state_unsupported_protocol_error(self):
        """Verify CPU state protocol error 0x81/0x84 does not raise and returns UNKNOWN - CPU state unavailable."""
        client = S7Client()
        client.connected = True
        client.client = MagicMock()
        
        # Simulate PLCSIM protocol error
        client.client.get_cpu_state.side_effect = Exception("S7 protocol error (class=0x84, code=0x04): The function cannot be performed")
        
        success, state, diag_msg = client.get_cpu_state()
        self.assertTrue(success, "CPU state query should return success=True for decoupled handling")
        self.assertEqual(state, "UNKNOWN — CPU state unavailable")
        self.assertIn("0x84", diag_msg)

    def test_05_tag_manager_polling_diagnostics(self):
        """Verify poll_tags updates diagnostics correctly and does not stay at Never."""
        plc_mgr = PLCManager()
        tm = plc_mgr.tag_manager
        
        # When polling is enabled but no table selected
        tm.set_polling(True, table_id=None)
        tm.poll_tags()
        self.assertNotEqual(tm.diagnostics["last_cycle"], "Never")
        self.assertEqual(tm.diagnostics["last_error"], "No active table selected")
        
        # When table selected with mock DB
        db = tm.db
        table_id = db.create_table("test_table", "test")
        tm.set_active_table(table_id)
        tm.poll_tags()
        self.assertEqual(tm.diagnostics["attempted"], 0)
        self.assertEqual(tm.diagnostics["last_error"], "No tags defined in active table")

        # Cleanup test table
        db.delete_table(table_id)
        plc_mgr._running = False

if __name__ == '__main__':
    unittest.main()
