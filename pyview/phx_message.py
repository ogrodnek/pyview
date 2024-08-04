from starlette.websockets import WebSocketDisconnect
from starlette.types import Message
import json


def parse_message(message: Message) -> tuple[str, str, str, str, dict]:
    if "text" in message:
        data = message["text"]
        [joinRef, mesageRef, topic, event, payload] = json.loads(data)
        return joinRef, mesageRef, topic, event, payload

    if "bytes" in message:
        data = message["bytes"]
        # TODO: need to handle these message types better
        return BinaryUploadSerDe().deserialize(data)  # type: ignore

    # {'type': 'websocket.disconnect', 'code': <CloseReason.NO_STATUS_RCVD: 1005>}
    # TODO handle: other errors?
    raise WebSocketDisconnect(message["code"])


import struct


class BinaryUploadSerDe:
    def deserialize(self, encoded_data: bytes) -> tuple[str, str, str, str, bytes]:
        offset = 0

        # Read the kind (1 byte)
        kind = struct.unpack_from("B", encoded_data, offset)[0]
        offset += 1

        # Read lengths (4 bytes total, 1 byte each)
        join_ref_length = struct.unpack_from("B", encoded_data, offset)[0]
        offset += 1
        ref_length = struct.unpack_from("B", encoded_data, offset)[0]
        offset += 1
        topic_length = struct.unpack_from("B", encoded_data, offset)[0]
        offset += 1
        event_length = struct.unpack_from("B", encoded_data, offset)[0]
        offset += 1

        # Read the strings
        join_ref = encoded_data[offset : offset + join_ref_length].decode("utf-8")
        offset += join_ref_length
        msg_ref = encoded_data[offset : offset + ref_length].decode("utf-8")
        offset += ref_length
        topic = encoded_data[offset : offset + topic_length].decode("utf-8")
        offset += topic_length
        event = encoded_data[offset : offset + event_length].decode("utf-8")
        offset += event_length

        # The remaining bytes are the payload
        payload = encoded_data[offset:]
        return join_ref, msg_ref, topic, event, payload
