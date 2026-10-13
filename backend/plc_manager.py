import time
import logging
import threading
import datetime
from backend.s7_client import S7Client
from backend.tag_manager import TagManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PLCManager:
    def __init__(self):
        self.plcs = {} # ID -> dict of config and state
        self.active_plc_id = None
        self._running = True
        self.tag_manager = TagManager(self)
        self.last_tag_poll = 0
        
        self._monitor_thread = threading.Thread(target=self._health_monitor_loop, daemon=True)
        self._monitor_thread.start()
        
    def add_plc(self, plc_id, name, ip, rack, slot, port):
        """Add or update a PLC configuration."""
        if plc_id not in self.plcs:
            self.plcs[plc_id] = {
                "id": plc_id,
                "client": S7Client(),
                "state": "DISCONNECTED",
                "diagnostics": [],
                "cpu_state": "UNKNOWN",
                "cpu_state_error": None,
                "last_s7_success_time": None,
                "last_error": None,
                "last_reconnect_attempt": 0,
                "last_logged_state": None,
                "last_logged_error": None
            }
        
        self.plcs[plc_id].update({
            "name": name,
            "ip": ip,
            "rack": int(rack),
            "slot": int(slot),
            "port": int(port)
        })
        return plc_id
        
    def get_plc(self, plc_id):
        return self.plcs.get(plc_id)
        
    def _health_monitor_loop(self):
        """Continuously monitor connection health and handle auto-recovery."""
        while self._running:
            try:
                current_time = time.time()
                for plc_id, plc in list(self.plcs.items()):
                    client = plc.get("client")
                    if not client: continue
                    
                    if plc["state"] == "CONNECTED":
                        # Perform lightweight health check
                        try:
                            success, state, diag_msg = client.get_cpu_state()
                            self.log_diagnostic(plc_id, "DEBUG CPU", "INFO", diag_msg)
                        except Exception as e:
                            success = True
                            state = "UNKNOWN — CPU state unavailable"
                            diag_msg = f"CPU_STATE raw=ERROR type={type(e).__name__} decoded=UNKNOWN ({e})"
                            self.log_diagnostic(plc_id, "DEBUG CPU", "INFO", diag_msg)
                            
                        # Update CPU state without disconnecting working S7 data client
                        if success:
                            plc["last_s7_success_time"] = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                            if plc["cpu_state"] != state:
                                plc["cpu_state"] = state
                                plc["cpu_state_error"] = None
                                self.log_diagnostic(plc_id, "CPU STATE", "PASS" if "RUN" in state or "STOP" in state else "INFO", state)
                            plc["last_logged_state"] = "CONNECTED"
                            plc["last_logged_error"] = None
                        else:
                            # CPU state query failed, but do NOT disconnect if client is still marked connected
                            plc["cpu_state"] = "UNKNOWN — CPU state unavailable"
                            plc["cpu_state_error"] = state
                            
                        # Check actual socket liveness if needed
                        if not getattr(client, "connected", False):
                            plc["state"] = "CONNECTION LOST"
                            if plc["last_logged_state"] != "CONNECTION LOST":
                                self.log_diagnostic(plc_id, "CONNECTION LOST", "FAIL", "S7 client disconnected")
                                plc["last_logged_state"] = "CONNECTION LOST"
                                plc["last_logged_error"] = "S7 client disconnected"
                            
                    elif plc["state"] in ["CONNECTION LOST", "CONNECTION FAILED"]:
                        # Throttle reconnects to once every 2 seconds
                        if current_time - plc.get("last_reconnect_attempt", 0) > 2.0:
                            plc["last_reconnect_attempt"] = current_time
                            
                            if plc["last_logged_state"] != "RECONNECTING":
                                self.log_diagnostic(plc_id, "RECONNECTING", "INFO", f"{plc['ip']}:{plc['port']}")
                                plc["last_logged_state"] = "RECONNECTING"
                                
                            # Lightweight TCP check first (0.2s timeout so we don't stall the background monitor!)
                            tcp_ok, tcp_err = client.test_tcp_connection(plc["ip"], plc["port"], timeout=0.200)
                            
                            if tcp_ok:
                                # Re-establish connection
                                success, msg, latency = client.connect(plc["ip"], plc["rack"], plc["slot"], plc["port"])
                                if success:
                                    plc["state"] = "CONNECTED"
                                    plc["last_s7_success_time"] = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                                    
                                    # Refresh CPU state immediately
                                    try:
                                        state_success, cpu_state, diag_msg = client.get_cpu_state()
                                        self.log_diagnostic(plc_id, "DEBUG CPU", "INFO", diag_msg)
                                    except Exception as e:
                                        state_success = True
                                        cpu_state = "UNKNOWN — CPU state unavailable"
                                        diag_msg = f"CPU_STATE raw=ERROR type={type(e).__name__} decoded=UNKNOWN ({e})"
                                        self.log_diagnostic(plc_id, "DEBUG CPU", "INFO", diag_msg)
                                        
                                    plc["cpu_state"] = cpu_state
                                    plc["cpu_state_error"] = None if state_success else cpu_state
                                    self.log_diagnostic(plc_id, "S7 RECONNECTED", "PASS", f"CPU {cpu_state}")
                                    plc["last_logged_state"] = "CONNECTED"
                                    plc["last_logged_error"] = None
                                else:
                                    plc["last_error"] = msg
                                    if plc["last_logged_error"] != msg:
                                        self.log_diagnostic(plc_id, "S7 RECONNECT FAILED", "FAIL", msg)
                                        plc["last_logged_error"] = msg
                                        plc["last_logged_state"] = "CONNECTION LOST"
                                        
                            if not tcp_ok:
                                plc["state"] = "CONNECTION LOST"
                
                # Check tag polling schedule
                if current_time - self.last_tag_poll >= 0.5:
                    self.tag_manager.poll_tags()
                    self.last_tag_poll = time.time()
                    
            except Exception as e:
                logger.error(f"Error in health monitor loop: {e}", exc_info=True)
                print(f"[HEALTH MONITOR ERROR] {e}")
                
            time.sleep(0.150) # Sleep for 150ms to keep cycle time low but avoid pegging CPU
            
    def log_diagnostic(self, plc_id, operation, status, details=""):
        """Log a diagnostic event for a specific PLC."""
        plc = self.get_plc(plc_id)
        if not plc: return
        
        timestamp = time.strftime("%H:%M:%S")
        log_entry = {
            "time": timestamp,
            "operation": operation,
            "status": status,
            "details": details
        }
        
        # Keep last 50 logs
        plc["diagnostics"].append(log_entry)
        if len(plc["diagnostics"]) > 50:
            plc["diagnostics"].pop(0)
            
    def ping(self, plc_id):
        """Ping the configured IP."""
        plc = self.get_plc(plc_id)
        if not plc: return False, "PLC not found", 0
        
        ip = plc["ip"]
        client = plc["client"]
        
        success, msg, latency = client.ping(ip)
        status_str = "PASS" if success else "FAIL"
        
        details = f"{latency}ms" if success else msg
        self.log_diagnostic(plc_id, "PING", status_str, details)
        
        return success, msg, latency
        
    def test_s7_communication(self, plc_id):
        """Perform temporary connection, read CPU state, and disconnect."""
        plc = self.get_plc(plc_id)
        if not plc: return False, "PLC not found", 0, "UNKNOWN"
        
        client = plc["client"]
        
        # If already connected persistently, use that instead of reconnecting
        if client.connected:
            success, state, diag_msg = client.get_cpu_state()
            self.log_diagnostic(plc_id, "DEBUG CPU", "INFO", diag_msg)
            if success:
                self.log_diagnostic(plc_id, "S7 COMM TEST", "PASS", "Using existing connection")
                self.log_diagnostic(plc_id, "CPU STATE", "PASS", state)
                return True, "Success", 0, state, None
                
        # Don't disconnect the active client! Create a temporary one for testing.
        from backend.s7_client import S7Client
        test_client = S7Client()
        
        ip = plc["ip"]
        rack = plc["rack"]
        slot = plc["slot"]
        port = plc["port"]
        
        success, msg, latency = test_client.connect(ip, rack, slot, port)
        if not success:
            self.log_diagnostic(plc_id, "S7 CONNECT", "FAIL", msg)
            return False, msg, latency, "UNKNOWN", msg
            
        self.log_diagnostic(plc_id, "S7 CONNECT", "PASS", f"{latency}ms")
        
        # Get CPU State
        state_success, state_msg, diag_msg = test_client.get_cpu_state()
        if state_success and ("RUN" in state_msg or "STOP" in state_msg):
            self.log_diagnostic(plc_id, "CPU STATE", "PASS", state_msg)
        else:
            self.log_diagnostic(plc_id, "CPU STATE", "INFO", state_msg)
            
        test_client.disconnect()
        
        return True, "S7 Communication Successful", latency, state_msg if state_success else "UNKNOWN — CPU state unavailable", None
        
    def connect(self, plc_id):
        """Establish persistent connection."""
        plc = self.get_plc(plc_id)
        if not plc: return False, "PLC not found"
        
        plc["state"] = "CONNECTING"
        client = plc["client"]
        
        success, msg, latency = client.connect(plc["ip"], plc["rack"], plc["slot"], plc["port"])
        
        if success:
            state_success, cpu_state, diag_msg = client.get_cpu_state()
            self.log_diagnostic(plc_id, "DEBUG CPU", "INFO", diag_msg)
            plc["state"] = "CONNECTED"
            
            if state_success and ("RUN" in cpu_state or "STOP" in cpu_state):
                plc["cpu_state"] = cpu_state
                plc["cpu_state_error"] = None
                self.log_diagnostic(plc_id, "CPU STATE", "PASS", cpu_state)
            else:
                plc["cpu_state"] = cpu_state if state_success else "UNKNOWN — CPU state unavailable"
                plc["cpu_state_error"] = None
                self.log_diagnostic(plc_id, "CPU STATE", "INFO", cpu_state)
                
            self.log_diagnostic(plc_id, "CONNECT", "PASS", f"{latency}ms")
            return True, "Connected"
        else:
            plc["state"] = "CONNECTION FAILED"
            self.log_diagnostic(plc_id, "CONNECT", "FAIL", msg)
            return False, msg
            
    def disconnect(self, plc_id):
        """Disconnect persistent connection."""
        plc = self.get_plc(plc_id)
        if not plc: return False, "PLC not found"
        
        plc["state"] = "DISCONNECTING"
        client = plc["client"]
        
        client.disconnect()
        plc["state"] = "DISCONNECTED"
        plc["cpu_state"] = "UNKNOWN"
        plc["cpu_state_error"] = None
        
        self.log_diagnostic(plc_id, "DISCONNECT", "PASS", "")
        return True, "Disconnected"
        
    def reconnect(self, plc_id):
        """Disconnect and reconnect."""
        self.disconnect(plc_id)
        # Add slight delay to allow socket to fully close on OS level if needed
        time.sleep(0.5)
        return self.connect(plc_id)
        
    def get_status(self, plc_id):
        """Get full status and diagnostics for UI."""
        plc = self.get_plc(plc_id)
        if not plc: return None
        
        return {
            "id": plc["id"],
            "name": plc["name"],
            "ip": plc["ip"],
            "rack": plc["rack"],
            "slot": plc["slot"],
            "port": plc["port"],
            "state": plc["state"],
            "cpu_state": plc["cpu_state"],
            "cpu_state_error": plc.get("cpu_state_error"),
            "last_s7_success_time": plc.get("last_s7_success_time"),
            "last_error": plc.get("last_error"),
            "diagnostics": plc["diagnostics"]
        }
