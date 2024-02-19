#!/usr/bin/env python
from dissect.cstruct import cstruct, dumpstruct

import json
import socket
import struct

class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='surrogateescape')
        return json.JSONEncoder.default(self, obj)

protocol = cstruct()

protocol.load(
    """
enum AttackType : uint8 {
    ATK_OPT_DPORT =  7,
    ATK_OPT_DOMAIN  =  8,
    ATK_OPT_NUM_SOCKETS =  24,
};

struct AttackTarget {
    DWORD   ipv4;
    BYTE    netmask;
};

struct AttackOption {
    AttackType   type;
    uint8   value_length;
    char    value[value_length];
};

struct MiraiAttack {
    uint16  total_length;
    uint32  duration;
    uint8   attack_id;
    uint8   target_count;
    AttackTarget targets[target_count];
    uint8   num_opts;
    AttackOption attack_options[num_opts];
};
"""
)

protocol.endian = ">"

if __name__ == "__main__":
    data = b"\x000\x00\x00\x00d\n\x01\x08\x08\x08\x08 \x03\x08\x16http://www.example.com\x07\x0280\x18\x045000"

    record = protocol.MiraiAttack(data)
    print(json.dumps(record, cls=CustomEncoder))