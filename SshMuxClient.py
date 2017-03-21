import os
import socket
import struct

from Buffer import Buffer

MUX_MSG_HELLO           = 0x00000001
MUX_C_NEW_SESSION       = 0x10000002
MUX_C_ALIVE_CHECK       = 0x10000004
MUX_C_TERMINATE         = 0x10000005
MUX_C_OPEN_FWD          = 0x10000006
MUX_C_CLOSE_FWD         = 0x10000007
MUX_C_NEW_STDIO_FWD     = 0x10000008
MUX_C_STOP_LISTENING    = 0x10000009
MUX_C_LIST_FWDS         = 0x1000000a
MUX_C_LIST_SESSIONS     = 0x1000000b
MUX_C_INFO              = 0x1000000c
MUX_S_OK                = 0x80000001
MUX_S_PERMISSION_DENIED = 0x80000002
MUX_S_FAILURE           = 0x80000003
MUX_S_EXIT_MESSAGE      = 0x80000004
MUX_S_ALIVE             = 0x80000005
MUX_S_SESSION_OPENED    = 0x80000006
MUX_S_REMOTE_PORT       = 0x80000007
MUX_S_TTY_ALLOC_FAIL    = 0x80000008
MUX_S_RESULT            = 0x80000009

MUX_FWD_LOCAL   = 1
MUX_FWD_REMOTE  = 2
MUX_FWD_DYNAMIC = 3

MUX_FWD_PORT_STREAMLOCAL = -2

SSHMUX_VER = 4

_fwd_types = {
    MUX_FWD_LOCAL:   'local',
    MUX_FWD_REMOTE:  'remote',
    MUX_FWD_DYNAMIC: 'dynamic'
}

_fwd_names = {
    'local':   MUX_FWD_LOCAL,
    'remote':  MUX_FWD_REMOTE,
    'dynamic': MUX_FWD_DYNAMIC
}

class SshMuxClient(object):


    def __init__(self, path):
        self.rid = 0
        self.path = path
        self.fd = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

    def _write_packet(self, buf):
        pkt = Buffer()
        pkt.put_str(buf)
        return self.fd.sendall(pkt)

    def _read_packet(self):
        m = Buffer(self.fd.recv(4))
        pktlen = m.get_int()
        return Buffer(self.fd.recv(pktlen))

    def connect(self, blocking=1):
        self.fd.connect(self.path)
        self.fd.setblocking(blocking)

        m = Buffer()
        m.put_int(MUX_MSG_HELLO)
        m.put_int(SSHMUX_VER)
        if self._write_packet(m) is not None:
            return (False, 'Can\'t send HELLO message')

        m = self._read_packet()

        mux_msg = m.get_int()
        if mux_msg != MUX_MSG_HELLO:
            return (False, 'Expected HELLO reply, got %u' % (mux_msg,))

        mux_ver = m.get_int()
        if mux_ver != SSHMUX_VER:
            return (False, 'Unsupported multiplexing protocol version %d (expected %d)' % (mux_ver, SSHMUX_VER))

        extensions = {}
        while len(m):
            name = m.get_str()
            value = m.get_str()
            extensions[name] = value
        return (True, extensions)

    def close(self):
        self.fd.close()

    def check(self):
        m = Buffer()
        m.put_int(MUX_C_ALIVE_CHECK)
        rid = self.rid
        self.rid += 1
        m.put_int(rid)

        if self._write_packet(m) is not None:
            return (False, 'Can\'t send ALIVE-CHECK request')

        m = self._read_packet()

        rep_msg = m.get_int()
        if rep_msg != MUX_S_ALIVE:
            return (False, 'Expected ALIVE reply, got %u' % (rep_msg,))

        rep_rid = m.get_int()
        if rep_rid != rid:
            return (False, 'Got unexpected request id %u, expected %u' % (rep_rid, rid))

        rep_pid = m.get_int()

        return (True, rep_pid)

    def exit(self):
        m = Buffer()
        m.put_int(MUX_C_TERMINATE)
        rid = self.rid
        self.rid += 1
        m.put_int(rid)

        if self._write_packet(m) is not None:
            return (False, 'Can\'t send TERMINATE request')

        # ignore reply
#        m = self._read_packet()
#
#        rep_msg = m.get_int()
#
#        rep_rid = m.get_int()
#        if rep_rid != rid:
#            return (False, 'Got unexpected request id %u, expected %u' % (rep_rid, rid))
#
#        if rep_msg != MUX_S_OK:
#            rep_reason = m.get_str()
#            if rep_msg == MUX_S_FAILURE:
#                return (False, 'Failure in EXIT message: %s' % (rep_reason,))
#            elif rep_msg == MUX_S_PERMISSION_DENIED:
#                return (False, 'Permission denied for EXIT message: %s' % (rep_reason,))
#            return (False, 'Unexpected server reply, got %u' % (rep_msg,))

        return (True, None)

    def stop(self):
        m = Buffer()
        m.put_int(MUX_C_STOP_LISTENING)
        rid = self.rid
        self.rid += 1
        m.put_int(rid)

        if self._write_packet(m) is not None:
            return (False, 'Can\'t send STOP-LISTENING request')

        m = self._read_packet()

        rep_msg = m.get_int()

        rep_rid = m.get_int()
        if rep_rid != rid:
            return (False, 'Got unexpected request id %u, expected %u' % (rep_rid, rid))

        if rep_msg != MUX_S_OK:
            rep_reason = m.get_str()
            if rep_msg == MUX_S_FAILURE:
                return (False, 'Failure in STOP message: %s' % (rep_reason,))
            elif rep_msg == MUX_S_PERMISSION_DENIED:
                return (False, 'Permission denied for STOP message: %s' % (rep_reason,))
            return (False, 'Unexpected server reply, got %u' % (rep_msg,))

        return (True, None)

    def forward(self, mode, ftype, listen_host, listen_port, connect_host, connect_port):
        m = Buffer()
        if mode:
            n = 'OPEN'
            m.put_int(MUX_C_OPEN_FWD)
        else:
            n = 'CLOSE'
            m.put_int(MUX_C_CLOSE_FWD)
        rid = self.rid
        self.rid += 1
        m.put_int(rid)

        if isinstance(ftype, basestring):
            assert ftype in _fwd_names, 'Invalid forward type %s' % (ftype,)
            ftype = _fwd_names[ftype]
        m.put_int(ftype)
        m.put_str(listen_host)
        m.put_int(listen_port)
        m.put_str(connect_host)
        m.put_int(connect_port)

        if self._write_packet(m) is not None:
            return (False, 'Can\'t send %s-FORWARD request' % (n,))

        m = self._read_packet()

        rep_msg = m.get_int()

        rep_rid = m.get_int()
        if rep_rid != rid:
            return (False, 'Got unexpected request id %u, expected %u' % (rep_rid, rid))

        if rep_msg != MUX_S_OK and rep_msg != MUX_S_REMOTE_PORT:
            rep_reason = m.get_str()
            if rep_msg == MUX_S_FAILURE:
                return (False, 'Failure in %s-FORWARD request: %s' % (n, rep_reason,))
            elif rep_msg == MUX_S_PERMISSION_DENIED:
                return (False, 'Permission denied for %s-FORWARD request: %s' % (n, rep_reason,))
            return (False, 'Unexpected server reply, got %u' % (rep_msg,))

        if ftype == MUX_FWD_REMOTE and listen_port == 0:
            if rep_msg != MUX_S_REMOTE_PORT:
                return (False, 'Expected remote port reply, got %u' % (rep_msg,))
            rep_port = m.get_int()
            return (True, rep_port)

        return (True, None)

    def open_forward(self, ftype, listen_host, listen_port, connect_host, connect_port):
        return self.forward(True, ftype, listen_host, listen_port, connect_host, connect_port)

    def close_forward(self, ftype, listen_host, listen_port, connect_host, connect_port):
        return self.forward(False, ftype, listen_host, listen_port, connect_host, connect_port)

    def forwards(self):
        m = Buffer()
        m.put_int(MUX_C_LIST_FWDS)
        rid = self.rid
        self.rid += 1
        m.put_int(rid)

        if self._write_packet(m) is not None:
            return (False, 'Can\'t send LIST-FORWARDS request')

        m = self._read_packet()

        rep_msg = m.get_int()

        rep_rid = m.get_int()
        if rep_rid != rid:
            return (False, 'Got unexpected request id %u, expected %u' % (rep_rid, rid))

        if rep_msg != MUX_S_RESULT:
            rep_reason = m.get_str()
            if rep_msg == MUX_S_FAILURE:
                return (False, 'Failure in LIST-FORWARDS request: %s' % (rep_reason,))
            elif rep_msg == MUX_S_PERMISSION_DENIED:
                return (False, 'Permission denied for LIST-FORWARDS request: %s' % (rep_reason,))
            return (False, 'Unexpected server reply, got %u' % (rep_msg,))

        fwds = []
        while len(m):
            fid = m.get_int()
            ftype = m.get_int()
            listen_host = m.get_str()
            listen_port = m.get_int()
            connect_host = m.get_str()
            connect_port = m.get_int()

            if ftype == MUX_FWD_REMOTE and listen_port == 0:
                listen_port = m.get_int()

            fwds.append((fid, _fwd_types[ftype], listen_host, listen_port, connect_host, connect_port))
        return (True, fwds)

    def sessions(self):
        m = Buffer()
        m.put_int(MUX_C_LIST_SESSIONS)
        rid = self.rid
        self.rid += 1
        m.put_int(rid)

        if self._write_packet(m) is not None:
            return (False, 'Can\'t send LIST-SESSIONS request')

        m = self._read_packet()

        rep_msg = m.get_int()

        rep_rid = m.get_int()
        if rep_rid != rid:
            return (False, 'Got unexpected request id %u, expected %u' % (rep_rid, rid))

        if rep_msg != MUX_S_RESULT:
            rep_reason = m.get_str()
            if rep_msg == MUX_S_FAILURE:
                return (False, 'Failure in LIST-SESSIONS request: %s' % (rep_reason,))
            elif rep_msg == MUX_S_PERMISSION_DENIED:
                return (False, 'Permission denied for LIST-SESSIONS request: %s' % (rep_reason,))
            return (False, 'Unexpected server reply, got %u' % (rep_msg,))

        sessions = []
        while len(m):
            sid = m.get_int();
            stype = m.get_int();
            rid = m.get_int();
            cid = m.get_int();
            tname = m.get_str();
            rname = m.get_str();

            sessions.append((sid, stype, rid, cid, tname, rname))

        return (True, sessions)

    def info(self, fmt):
        m = Buffer()
        m.put_int(MUX_C_INFO)
        rid = self.rid
        self.rid += 1
        m.put_int(rid)
        m.put_str(fmt)

        if self._write_packet(m) is not None:
            return (False, 'Can\'t send INFO request')

        m = self._read_packet()

        rep_msg = m.get_int()

        rep_rid = m.get_int()
        if rep_rid != rid:
            return (False, 'Got unexpected request id %u, expected %u' % (rep_rid, rid))

        if rep_msg != MUX_S_RESULT:
            rep_reason = m.get_str()
            if rep_msg == MUX_S_FAILURE:
                return (False, rep_reason)
            return (False, 'Expected INFO reply, got %x' % (rep_msg,))

        rep_str = m.get_str()

        return (True, rep_str)
