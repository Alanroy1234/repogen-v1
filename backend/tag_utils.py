import snap7.util
import snap7.type
import struct

def get_data_type_size(data_type):
    """Returns the size in bytes for a given S7 data type."""
    data_type = data_type.upper()
    if data_type in ["BOOL", "BYTE", "SINT", "USINT"]:
        return 1
    elif data_type in ["INT", "UINT", "WORD"]:
        return 2
    elif data_type in ["DINT", "UDINT", "DWORD", "REAL"]:
        return 4
    else:
        raise ValueError(f"Unsupported data type: {data_type}")

def parse_address(address_str, data_type):
    """
    Parses a pure address string (e.g., '0', '0.0', '10.5') into byte and bit offset.
    Does not parse DB numbers or M/I/Q prefixes since those are configured separately.
    Returns (byte_offset, bit_offset).
    """
    import re
    address_str = address_str.strip().upper()
    
    # Strip DB number prefix if present (e.g. "DB1.DBD4" -> "DBD4")
    db_match = re.match(r"^DB\d+\.(.+)$", address_str)
    if db_match:
        address_str = db_match.group(1)
        
    # Strip any prefix just in case the user types "M0.0", "MW0", or "DBD4" instead of "0.0"
    if address_str.startswith(("DBX", "DBD", "DBW", "DBB")):
        address_str = address_str[3:]
    elif address_str.startswith(("M", "I", "Q", "A", "E")):
        if len(address_str) > 1 and address_str[1] in ["B", "W", "D"]:
            address_str = address_str[2:]
        else:
            address_str = address_str[1:]
            
    if data_type.upper() == "BOOL":
        if "." not in address_str:
            raise ValueError(f"BOOL address must specify a bit offset (e.g. '0.0')")
        parts = address_str.split(".")
        if len(parts) != 2:
            raise ValueError(f"Invalid BOOL address format: {address_str}")
        byte_offset = int(parts[0])
        bit_offset = int(parts[1])
        if bit_offset < 0 or bit_offset > 7:
            raise ValueError(f"Bit offset must be between 0 and 7. Got {bit_offset}")
        return byte_offset, bit_offset
    else:
        # Non-BOOL type
        if "." in address_str:
            parts = address_str.split(".")
            if len(parts) == 2 and parts[1] == "0":
                byte_offset = int(parts[0])
            else:
                raise ValueError(f"Data type {data_type} cannot have a non-zero bit offset.")
        else:
            byte_offset = int(address_str)
        return byte_offset, 0

def decode_value(buffer, data_type, bit_offset=0):
    """Decodes a bytearray into a Python value using snap7.util."""
    data_type = data_type.upper()
    
    if data_type == "BOOL":
        return snap7.util.get_bool(buffer, 0, bit_offset)
        
    elif data_type == "BYTE":
        return snap7.util.get_usint(buffer, 0)
    elif data_type == "SINT":
        return snap7.util.get_sint(buffer, 0)
    elif data_type == "USINT":
        return snap7.util.get_usint(buffer, 0)
        
    elif data_type == "INT":
        return snap7.util.get_int(buffer, 0)
    elif data_type == "UINT":
        return snap7.util.get_uint(buffer, 0)
    elif data_type == "WORD":
        return snap7.util.get_word(buffer, 0)
        
    elif data_type == "DINT":
        return snap7.util.get_dint(buffer, 0)
    elif data_type == "UDINT":
        return snap7.util.get_udint(buffer, 0)
    elif data_type == "DWORD":
        return snap7.util.get_dword(buffer, 0)
    elif data_type == "REAL":
        return snap7.util.get_real(buffer, 0)
        
    else:
        raise ValueError(f"Unsupported data type for decoding: {data_type}")

def encode_value(value, data_type, buffer, bit_offset=0):
    """Encodes a Python value into an existing bytearray using snap7.util."""
    data_type = data_type.upper()
    
    try:
        if data_type == "BOOL":
            # For BOOL, the value must be cast to boolean
            val = bool(value)
            snap7.util.set_bool(buffer, 0, bit_offset, val)
            
        elif data_type == "BYTE":
            val = int(value)
            snap7.util.set_usint(buffer, 0, val)
        elif data_type == "SINT":
            val = int(value)
            snap7.util.set_sint(buffer, 0, val)
        elif data_type == "USINT":
            val = int(value)
            snap7.util.set_usint(buffer, 0, val)
            
        elif data_type == "INT":
            val = int(value)
            snap7.util.set_int(buffer, 0, val)
        elif data_type == "UINT":
            val = int(value)
            snap7.util.set_uint(buffer, 0, val)
        elif data_type == "WORD":
            val = int(value)
            # word expects bytearray length 2, set_word uses struct unpack internally or assigns it
            snap7.util.set_word(buffer, 0, val)
            
        elif data_type == "DINT":
            val = int(value)
            snap7.util.set_dint(buffer, 0, val)
        elif data_type == "UDINT":
            val = int(value)
            snap7.util.set_udint(buffer, 0, val)
        elif data_type == "DWORD":
            val = int(value)
            snap7.util.set_dword(buffer, 0, val)
        elif data_type == "REAL":
            val = float(value)
            snap7.util.set_real(buffer, 0, val)
            
        else:
            raise ValueError(f"Unsupported data type for encoding: {data_type}")
            
    except ValueError as e:
        raise ValueError(f"Cannot cast {value} to {data_type}: {str(e)}")
    except struct.error as e:
        raise ValueError(f"Value {value} is out of bounds for {data_type}")
