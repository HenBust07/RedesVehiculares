"""Bus compartido y sondas distintas; los ID seriales heredados no son buses."""

BUS_ID = "BUS_001"
PROBE_IDS = {"BUS_001": "SENSOR_01", "BUS_002": "SENSOR_02"}


def probe_label(protocol_id):
    return PROBE_IDS.get(protocol_id, protocol_id)


def assignment(protocol_id):
    return {"bus_id": BUS_ID, "probe_id": PROBE_IDS[protocol_id]}
