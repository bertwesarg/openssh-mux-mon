#!/usr/bin/env python

import os
import sys
import socket
import struct

import SshMuxClient

if __name__ == '__main__':
    try:
        muxclient = SshMuxClient.SshMuxClient(sys.argv[1])
    except:
        print >>sys.stderr, 'Can\'t create mux client.'
        sys.exit(1)
    res, val = muxclient.connect()
    if not res:
        print >>sys.stderr, val
        sys.exit(1)
    print 'Successfully connected to mux master: %s' % (sys.argv[1],)
    for name in val:
        print 'Unrecognised master extension "%s"' % (name)

    try:
        cmd = sys.argv[2]
    except:
            cmd = 'check'

    if cmd == 'check':
        res, val = muxclient.check()
        if not res:
            print >>sys.stderr, val
            sys.exit(1)
        print 'MUX master alive with pid %u' % (val,)

    elif cmd == 'exit':
        res, val = muxclient.exit()
        if not res:
            print >>sys.stderr, val
            sys.exit(1)
        print 'MUX master temrinated'

    elif cmd == 'stop':
        res, val = muxclient.stop()
        if not res:
            print >>sys.stderr, val
            sys.exit(1)
        print 'MUX master stopped listing for mux clients'

    elif cmd == 'forward' or cmd == 'cancel':
        mode = True
        if cmd == 'cancel':
            mode = False

        fwd_types = {
            'local':   SshMuxClient.MUX_FWD_LOCAL,
            'remote':  SshMuxClient.MUX_FWD_REMOTE,
            'dynamic': SshMuxClient.MUX_FWD_DYNAMIC
        }

        type = sys.argv[3]
        if type not in fwd_types.keys():
            print >>sys.stderr, 'Invalid forwarding type %s' % (type, )
            sys.exit(1)

        if len(sys.argv) != 5:
            print >>sys.stderr, 'Invalid number of arguments'
            sys.exit(1)

        fwdarg = sys.argv[4].split(':')

        listen_host = ''
        listen_port = 0
        connect_host = ''
        connect_port = 0

        if len(fwdarg) == 1:
            if type != 'dynamic':
                print >>sys.stderr, 'Invalid number of arguments for non dynamic forwarding'
                sys.exit(1)
            listen_port = fwdarg[0]
            connect_host = 'socks'

        if len(fwdarg) == 2:
            if type != 'dynamic':
                print >>sys.stderr, 'Invalid number of arguments for non dynamic forwarding'
                sys.exit(1)
            listen_host = fwdarg[0]
            listen_port = int(fwdarg[1])
            connect_host = 'socks'

        if len(fwdarg) == 3:
            if type == 'dynamic':
                print >>sys.stderr, 'Invalid number of arguments for dynamic forwarding'
                sys.exit(1)
            listen_port = int(fwdarg[0])
            connect_host = fwdarg[1]
            connect_port = int(fwdarg[2])

        if len(fwdarg) == 4:
            if type != 'dynamic':
                print >>sys.stderr, 'Invalid number of arguments for dynamic forwarding'
                sys.exit(1)
            listen_host = fwdarg[0]
            listen_port = int(fwdarg[1])
            connect_host = fwdarg[2]
            connect_port = int(fwdarg[3])

        if type != 'dynamic' and connect_port < 0:
            print >>sys.stderr, 'Invalid connecting port for forwarding: %u' % (connect_port,)
            sys.exit(1)

        res, val = muxclient.forward(
            mode,
            fwd_types[type],
            listen_host,
            listen_port,
            connect_host,
            connect_port)
        if not res:
            print >>sys.stderr, val
            sys.exit(1)
        if type == 'remote' and listen_port == 0:
            print 'Allocated port for dynamic forwarding to %s:%u: %u' % (connect_host, connect_port, val)
        print 'Request succeeded.'

    elif cmd == 'forwards':
        res, val = muxclient.forwards()
        if not res:
            print >>sys.stderr, val
            sys.exit(1)

        print 'List of forwardings:'
        for fwd in val:
            fid, \
            ftype, \
            listen_host, \
            listen_port, \
            connect_host, \
            connect_port = fwd
            print '  %u: %s forwarding %s:%u -> %s:%u' % (fid, ftype, listen_host, listen_port, connect_host, connect_port)

    elif cmd == 'sessions':
        res, val = muxclient.sessions()
        if not res:
            print >>sys.stderr, val
            sys.exit(1)

        print 'List of sessions:'
        for session in val:
            sid, \
            stype, \
            rid, \
            cid, \
            name, \
            rname = session
            print '  #%u %u %u %u %s: %s' % (sid,
                stype,
                rid,
                cid,
                name,
                rname)

    elif cmd == 'info':
        if len(sys.argv) != 4:
            print >>sys.stderr, 'Invalid number of arguments'
            sys.exit(1)

        res, val = muxclient.info(sys.argv[3])
        if not res:
            print >>sys.stderr, 'Invalid format: %s' % val
            sys.exit(1)
        print 'MUX info replay:'
        print val

    else:
        print >>sys.stderr, 'Invalid mux command: %s' % (cmd,)
        muxclient.close()
        sys.exit(1)

    muxclient.close()
