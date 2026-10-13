import json

d = {
    1: {
        "value": None,
        "quality": "UNKNOWN",
        "timestamp": None,
        "error": None,
        "latency": 0
    }
}
print(json.dumps(d))
