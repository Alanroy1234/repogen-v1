import snap7
try:
    from snap7.error import S7Error as Snap7Exception
except ImportError:
    try:
        from snap7.snap7exceptions import Snap7Exception
    except ImportError:
        try:
            from snap7.exceptions import Snap7Exception
        except ImportError:
            class Snap7Exception(Exception):
                pass
import time
import socket
import subprocess
import platform
import threading

class S7Client:
    def __init__(self):
        self.client = snap7.client.Client()
        self.connected = False
        self._lock = threading.Lock()
        
    def ping(self, ip_address, timeout=2.0):
        """Perform an ICMP ping to the target IP using the OS ping command."""
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        command = ['ping', param, '1', '-w', str(int(timeout * 1000)), ip_address]
        
        start_time = time.time()
        try:
            # We use creationflags to prevent a console window from flashing in GUI mode on Windows
            creationflags = 0
            if platform.system().lower() == 'windows':
                creationflags = subprocess.CREATE_NO_WINDOW
                
            result = subprocess.run(
                command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                creationflags=creationflags,
                text=True
            )
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            if result.returncode == 0:
                # Basic check to avoid false positives where ping succeeds but reports destination unreachable
                if "unreachable" in result.stdout.lower() or "timeout" in result.stdout.lower():
                    return False, "Destination host unreachable", elapsed_ms
                return True, "Success", elapsed_ms
            else:
                return False, f"Ping failed (code {result.returncode})", elapsed_ms
        except Exception as e:
            return False, str(e), int((time.time() - start_time) * 1000)

    def test_tcp_connection(self, ip, port, timeout=2.0):
        """Test if the TCP port is open before attempting S7 connection to provide better diagnostics."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect((ip, port))
            return True, "TCP Port Open"
        except socket.timeout:
            return False, f"TCP connection to {ip}:{port} timed out."
        except ConnectionRefusedError:
            return False, f"TCP connection to {ip}:{port} was refused."
        except Exception as e:
            return False, f"TCP connection failed: {str(e)}"
            
    def connect(self, ip, rack, slot, port=102):
        """Connect to the S7 PLC."""
        with self._lock:
            if self.connected:
                # We call the internal logic to avoid deadlock since self.disconnect() acquires lock
                try:
                    self.client.disconnect()
                except Exception:
                    pass
                finally:
                    self.connected = False
                
            # Recreate the client object to ensure a completely clean state
            # This prevents stale sockets from locking up NetToPLCSim
            try:
                if hasattr(self.client, 'destroy'):
                    self.client.destroy()
            except Exception:
                pass
            self.client = snap7.client.Client()
            
            # Set timeout to 200ms to meet sub-250ms detection constraint
            try:
                self.client.set_param(5, 200) # RecvTimeout
                self.client.set_param(4, 200) # SendTimeout
                self.client.set_param(3, 200) # PingTimeout
            except Exception:
                pass # Just in case the installed version doesn't support it
                
            # First test if port is reachable for better error reporting
            tcp_ok, tcp_err = self.test_tcp_connection(ip, port)
            if not tcp_ok:
                return False, tcp_err, 0
                
            start_time = time.time()
            try:
                # Connect
                self.client.connect(ip, rack, slot, tcp_port=port)
                self.connected = True
                elapsed_ms = int((time.time() - start_time) * 1000)
                return True, "Connected successfully", elapsed_ms
            except Snap7Exception as e:
                return False, f"S7 connection failed: {str(e)}", int((time.time() - start_time) * 1000)
            except Exception as e:
                return False, f"Unexpected error during connection: {str(e)}", int((time.time() - start_time) * 1000)

    def disconnect(self):
        """Disconnect from the PLC."""
        with self._lock:
            if getattr(self, 'connected', False):
                try:
                    self.client.disconnect()
                except Exception:
                    pass
                finally:
                    self.connected = False
                    
            # Force recreation of the client to clean up stale sockets
            try:
                if hasattr(self.client, 'destroy'):
                    self.client.destroy()
            except Exception:
                pass
            self.client = snap7.client.Client()
            return True, "Disconnected"
        
    def decode_cpu_state(self, raw_state):
        """Decode the raw CPU state returned by snap7."""
        if isinstance(raw_state, str):
            state_upper = raw_state.upper()
            if "RUN" in state_upper: return "RUN"
            if "STOP" in state_upper: return "STOP"
            return "UNKNOWN"
            
        if hasattr(raw_state, 'name'):
            name_upper = raw_state.name.upper()
            if "RUN" in name_upper: return "RUN"
            if "STOP" in name_upper: return "STOP"
            return "UNKNOWN"
            
        if isinstance(raw_state, int):
            if raw_state == 8: return "RUN"
            if raw_state == 4: return "STOP"
            return "UNKNOWN"
            
        return "UNKNOWN"

    def get_cpu_state(self):
        """Retrieve the CPU state."""
        with self._lock:
            if not getattr(self, 'connected', False):
                return False, "Not connected", "CPU_STATE Not connected"
                
            try:
                # 1. Call snap7 API directly
                raw_state = self.client.get_cpu_state()
                raw_type = type(raw_state).__name__
                
                # 2. Decode using dedicated function
                decoded = self.decode_cpu_state(raw_state)
                
                # 3. Log diagnostic format
                diagnostic_msg = f"CPU_STATE_DIAG_V2 raw={raw_state} type={raw_type} decoded={decoded}"
                print(diagnostic_msg)
                
                if decoded in ["RUN", "STOP"]:
                    # Return the diagnostic msg temporarily so it shows in the UI log
                    return True, decoded, diagnostic_msg
                else:
                    return True, f"UNKNOWN ({raw_state})", diagnostic_msg
                    
            except Exception as e:
                error_type = type(e).__name__
                error_str = str(e)
                diagnostic_msg = f"CPU_STATE_DIAG_V2 raw=ERROR type={error_type} decoded=UNKNOWN ({error_str})"
                print(diagnostic_msg)
                
                # If target does not support CPU state retrieval, do not treat as connection failure
                error_lower = error_str.lower()
                if ("s7 protocol error" in error_lower or 
                    "the function cannot be performed" in error_lower or 
                    "job pending" in error_lower or 
                    "service is not implemented" in error_lower or
                    "0x81" in error_lower or
                    "0x84" in error_lower):
                    return True, "UNKNOWN — CPU state unavailable", diagnostic_msg
                    
                return False, f"Failed: {error_str}", diagnostic_msg

    def _get_area_enum(self, area_str):
        area_str = area_str.upper()
        if area_str in ["M", "MK"]: return snap7.type.Areas.MK
        if area_str in ["I", "E", "PE"]: return snap7.type.Areas.PE
        if area_str in ["Q", "A", "PA"]: return snap7.type.Areas.PA
        if area_str == "DB": return snap7.type.Areas.DB
        raise ValueError(f"Unknown area: {area_str}")

    def read_tag(self, area_str, db_number, byte_offset, bit_offset, data_type):
        """Read a tag value from the PLC."""
        import backend.tag_utils as tag_utils
        
        with self._lock:
            if not getattr(self, 'connected', False):
                return False, "Not connected"
            
            try:
                area = self._get_area_enum(area_str)
                size = tag_utils.get_data_type_size(data_type)
                
                start_time = time.time()
                # read_area(area, dbnumber, start, size)
                buffer = self.client.read_area(area, db_number, byte_offset, size)
                latency = int((time.time() - start_time) * 1000)
                
                val = tag_utils.decode_value(buffer, data_type, bit_offset)
                
                # Diagnostic logging
                diag = f"device=default, area={area_str}, db={db_number}, byte_offset={byte_offset}, bit_offset={bit_offset}, data_type={data_type}"
                print(f"[READ TAG] {diag}")
                print(f"[READ SUCCESS] Raw bytes: {buffer.hex()}, Decoded: {val}, Latency: {latency}ms")
                
                return True, val
                
            except Snap7Exception as e:
                print(f"[READ ERROR] {str(e)}")
                return False, f"S7 Error: {str(e)}"
            except Exception as e:
                print(f"[READ ERROR] {str(e)}")
                return False, str(e)

    def write_tag(self, area_str, db_number, byte_offset, bit_offset, data_type, value):
        """Write a tag value to the PLC with read-modify-write for BOOL."""
        import backend.tag_utils as tag_utils
        
        with self._lock:
            if not getattr(self, 'connected', False):
                return False, "Not connected"
                
            try:
                area = self._get_area_enum(area_str)
                size = tag_utils.get_data_type_size(data_type)
                
                diag = f"device=default, area={area_str}, db={db_number}, byte_offset={byte_offset}, bit_offset={bit_offset}, data_type={data_type}"
                print(f"[WRITE TAG] {diag}")
                print(f"[WRITE REQUEST] Value: {value}")
                
                if data_type.upper() == "BOOL":
                    # Read-modify-write for BOOL to prevent adjacent bit corruption
                    buffer = self.client.read_area(area, db_number, byte_offset, 1)
                    tag_utils.encode_value(value, data_type, buffer, bit_offset)
                    print(f"[WRITE ENCODED] Raw bytes: {buffer.hex()}")
                    self.client.write_area(area, db_number, byte_offset, buffer)
                else:
                    buffer = bytearray(size)
                    tag_utils.encode_value(value, data_type, buffer, 0)
                    print(f"[WRITE ENCODED] Raw bytes: {buffer.hex()}")
                    self.client.write_area(area, db_number, byte_offset, buffer)
                    
                print("[WRITE SUCCESS]")
                return True, "Success"
                
            except Snap7Exception as e:
                print(f"[WRITE ERROR] {str(e)}")
                return False, f"S7 Error: {str(e)}"
            except Exception as e:
                print(f"[WRITE ERROR] {str(e)}")
                return False, str(e)
