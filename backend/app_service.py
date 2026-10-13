from backend.plc_manager import PLCManager
import logging

logger = logging.getLogger(__name__)

class AppService:
    def __init__(self):
        self.manager = PLCManager()
        # Create a default PLC configuration for Phase 1
        self.manager.add_plc("default", "Test PLC", "192.168.0.1", 0, 1, 102)
        
    def save_config(self, ip, rack, slot, port):
        """Update the configuration from UI."""
        self.manager.add_plc("default", "Test PLC", ip, rack, slot, port)
        return True
        
    def ping(self, ip, rack, slot, port):
        self.save_config(ip, rack, slot, port)
        success, msg, latency = self.manager.ping("default")
        return {
            "success": success,
            "message": msg,
            "latency": latency
        }
        
    def test_s7_communication(self, ip, rack, slot, port):
        self.save_config(ip, rack, slot, port)
        success, msg, latency, cpu_state, cpu_state_error = self.manager.test_s7_communication("default")
        return {
            "success": success,
            "message": msg,
            "latency": latency,
            "cpu_state": cpu_state,
            "cpu_state_error": cpu_state_error
        }
        
    def connect(self, ip, rack, slot, port):
        self.save_config(ip, rack, slot, port)
        success, msg = self.manager.connect("default")
        return {
            "success": success,
            "message": msg
        }
        
    def disconnect(self):
        success, msg = self.manager.disconnect("default")
        return {
            "success": success,
            "message": msg
        }
        
    def reconnect(self, ip, rack, slot, port):
        self.save_config(ip, rack, slot, port)
        success, msg = self.manager.reconnect("default")
        return {
            "success": success,
            "message": msg
        }
        
    def get_status(self):
        """Poll function for UI to get current state and logs."""
        return self.manager.get_status("default")

    # --- Tag Tables ---
    def get_all_tables(self):
        return self.manager.tag_manager.db.get_all_tables()

    def create_table(self, name, description=""):
        return self.manager.tag_manager.db.create_table(name, description)

    def update_table(self, table_id, name, description=""):
        self.manager.tag_manager.db.update_table(table_id, name, description)
        return True

    def delete_table(self, table_id):
        self.manager.tag_manager.db.delete_table(table_id)
        if self.manager.tag_manager.active_table_id == table_id:
            self.manager.tag_manager.set_active_table(None)
        return True

    # --- Tags ---
    def get_tags_for_table(self, table_id):
        return self.manager.tag_manager.db.get_tags_for_table(table_id)

    def create_tag(self, table_id, name, area, db_number, address, data_type, access_mode, description=""):
        res = self.manager.tag_manager.db.create_tag(table_id, name, area, db_number, address, data_type, access_mode, description)
        if self.manager.tag_manager.active_table_id == table_id:
            self.manager.tag_manager.set_active_table(table_id) # reload
        return res

    def update_tag(self, tag_id, name, area, db_number, address, data_type, access_mode, description=""):
        self.manager.tag_manager.db.update_tag(tag_id, name, area, db_number, address, data_type, access_mode, description)
        if self.manager.tag_manager.active_table_id is not None:
            self.manager.tag_manager.set_active_table(self.manager.tag_manager.active_table_id)
        return True

    def delete_tag(self, tag_id):
        self.manager.tag_manager.db.delete_tag(tag_id)
        if self.manager.tag_manager.active_table_id is not None:
            self.manager.tag_manager.set_active_table(self.manager.tag_manager.active_table_id)
        return True

    # --- Live Tags / Polling ---
    def set_active_table(self, table_id):
        self.manager.tag_manager.set_active_table(table_id)
        return True

    def set_polling(self, enabled, table_id=None):
        self.manager.tag_manager.set_polling(enabled, table_id)
        return True

    def get_live_tags(self):
        return {
            "tags": self.manager.tag_manager.live_tags,
            "diagnostics": self.manager.tag_manager.diagnostics
        }

    def write_tag(self, tag_id, value):
        success, msg = self.manager.tag_manager.write_tag(tag_id, value)
        return {
            "success": success,
            "message": msg
        }
