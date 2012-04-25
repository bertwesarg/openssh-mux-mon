import os
import sys
import socket
import struct

from SshMuxClient import SshMuxClient

if __name__ == '__main__':
    try:
        muxclient = SshMuxClient(sys.argv[1])
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

    if cmd == 'exit':
        res, val = muxclient.exit()
        if not res:
            print >>sys.stderr, val
            sys.exit(1)
        print 'MUX master temrinated'

    if cmd == 'stop':
        res, val = muxclient.stop()
        if not res:
            print >>sys.stderr, val
            sys.exit(1)
        print 'MUX master stopped listing for mux clients'

    muxclient.close()
