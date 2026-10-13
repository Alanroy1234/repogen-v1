import time
from backend.database import Database
import backend.tag_utils as tag_utils

class TagManager:
    def __init__(self, plc_manager):
        self.db = Database()
        self.plc_manager = plc_manager
        
        # In-memory dict for live tag values
        # tag_id -> {"value": val, "quality": "GOOD"/"BAD", "timestamp": str, "error": str, "latency": int}
        self.live_tags = {}
        self.active_table_id = None
        self.polling_enabled = False
        self.diagnostics = {
            "last_cycle": "Never",
            "attempted": 0,
            "success": 0,
            "failed": 0,
            "last_error": "None"
        }

    def set_active_table(self, table_id):
        self.active_table_id = table_id
        self.live_tags.clear()
        
        if table_id:
            tags = self.db.get_tags_for_table(table_id)
            for t in tags:
                self.live_tags[t["id"]] = {
                    "value": None,
                    "quality": "UNKNOWN",
                    "timestamp": None,
                    "error": None,
                    "latency": 0
                }

    def set_polling(self, enabled, table_id=None):
        self.polling_enabled = enabled
        if table_id is not None:
            self.set_active_table(table_id)

    def poll_tags(self):
        """Called by plc_manager's background thread to read all active tags."""
        if not self.polling_enabled:
            return
            
        if not self.active_table_id:
            self.diagnostics["last_cycle"] = time.strftime("%H:%M:%S")
            self.diagnostics["last_error"] = "No active table selected"
            return
            
        tags = self.db.get_tags_for_table(self.active_table_id)
        attempted = len(tags)
        
        if attempted == 0:
            self.diagnostics["last_cycle"] = time.strftime("%H:%M:%S")
            self.diagnostics["attempted"] = 0
            self.diagnostics["success"] = 0
            self.diagnostics["failed"] = 0
            self.diagnostics["last_error"] = "No tags defined in active table"
            return
        
        plc = self.plc_manager.get_plc("default")
        if not plc or plc["state"] != "CONNECTED":
            for t in tags:
                self._update_live_tag(t["id"], None, "BAD", "PLC not connected", 0)
            self.diagnostics["last_cycle"] = time.strftime("%H:%M:%S")
            self.diagnostics["attempted"] = attempted
            self.diagnostics["success"] = 0
            self.diagnostics["failed"] = attempted
            self.diagnostics["last_error"] = "PLC not connected"
            return

        client = plc.get("client")
        if not client or not getattr(client, 'connected', False):
            for t in tags:
                self._update_live_tag(t["id"], None, "BAD", "S7 Client disconnected", 0)
            self.diagnostics["last_cycle"] = time.strftime("%H:%M:%S")
            self.diagnostics["attempted"] = attempted
            self.diagnostics["success"] = 0
            self.diagnostics["failed"] = attempted
            self.diagnostics["last_error"] = "S7 Client disconnected"
            return
            
        # Add visible diagnostics
        success_count = 0
        failed_count = 0
        last_error = "None"
            
        for t in tags:
            try:
                byte_offset, bit_offset = tag_utils.parse_address(t["address"], t["data_type"])
                
                start_time = time.time()
                success, val = client.read_tag(t["area"], t["db_number"] or 0, byte_offset, bit_offset, t["data_type"])
                latency = int((time.time() - start_time) * 1000)
                
                if success:
                    self._update_live_tag(t["id"], val, "GOOD", None, latency)
                    success_count += 1
                else:
                    self._update_live_tag(t["id"], None, "BAD", val, latency)
                    failed_count += 1
                    last_error = str(val)
                    
            except Exception as e:
                self._update_live_tag(t["id"], None, "BAD", str(e), 0)
                failed_count += 1
                last_error = str(e)
                
        # Update diagnostics
        self.diagnostics["last_cycle"] = time.strftime("%H:%M:%S")
        self.diagnostics["attempted"] = attempted
        self.diagnostics["success"] = success_count
        self.diagnostics["failed"] = failed_count
        self.diagnostics["last_error"] = last_error

    def _update_live_tag(self, tag_id, value, quality, error, latency):
        timestamp = time.strftime("%H:%M:%S")
        self.live_tags[tag_id] = {
            "value": value,
            "quality": quality,
            "timestamp": timestamp,
            "error": error,
            "latency": latency
        }

    def write_tag(self, tag_id, value):
        tag = None
        if self.active_table_id:
            tags = self.db.get_tags_for_table(self.active_table_id)
            tag = next((t for t in tags if t["id"] == tag_id), None)
            
        if not tag:
            tag = self.db.get_tag(tag_id)
            
        if not tag:
            return False, "Tag not found"
            
        if tag["access_mode"] == "Read Only":
            return False, "Tag is read only"
            
        plc = self.plc_manager.get_plc("default")
        if not plc or plc["state"] != "CONNECTED":
            return False, "PLC not connected"
            
        client = plc.get("client")
        if not client or not getattr(client, "connected", False):
            return False, "S7 client not connected"
        
        try:
            byte_offset, bit_offset = tag_utils.parse_address(tag["address"], tag["data_type"])
            success, msg = client.write_tag(tag["area"], tag["db_number"] or 0, byte_offset, bit_offset, tag["data_type"], value)
            
            if not success:
                return False, msg
                
            # Verify write by reading back
            success_read, val = client.read_tag(tag["area"], tag["db_number"] or 0, byte_offset, bit_offset, tag["data_type"])
            if not success_read:
                print(f"[VERIFICATION FAILED] Readback error: {val}")
                return False, f"Write verified failed (readback error): {val}"
                
            # floating point tolerance check or direct match
            if tag["data_type"].upper() == "REAL":
                if abs(float(val) - float(value)) > 0.001:
                    print(f"[VERIFICATION FAILED] Requested: {value}, Read back: {val}")
                    return False, f"Verification failed. Read back: {val}"
            else:
                if str(val).lower() != str(value).lower():
                    # Check boolean representations
                    if tag["data_type"].upper() == "BOOL":
                        val_bool = bool(val)
                        req_bool = str(value).lower() in ["true", "1"]
                        if val_bool != req_bool:
                            print(f"[VERIFICATION FAILED] Requested: {req_bool}, Read back: {val_bool}")
                            return False, f"Verification failed. Read back: {val_bool}"
                    else:
                        print(f"[VERIFICATION FAILED] Requested: {value}, Read back: {val}")
                        return False, f"Verification failed. Read back: {val}"
                        
            print("[VERIFICATION SUCCESS] Readback matches requested value.")
            return True, "WRITE VERIFIED"
            
        except Exception as e:
            print(f"[WRITE ERROR] Exception: {str(e)}")
            return False, str(e)
