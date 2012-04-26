import struct

class Buffer(bytearray):
    def put_int(self, i):
        self.extend(struct.pack('!I', i))

    def put_str(self, s):
        self += struct.pack('!I', len(s)) + s

    def get_int(self):
        assert len(self) >= 4, 'Buffer too small for int: %u' % (len(self),)
        i = struct.unpack('!I', str(self[:4]))[0]
        del self[:4]
        return i

    def get_str(self):
        l = self.get_int()
        assert len(self) >= l, 'Buffer too small for a string of length %u: %u' % (l, len(self),)
        s = str(self[:l])
        del self[:l]
        return s

    def clear(self):
        del self[:]

if __name__ == '__main__':
    b = Buffer()
    b.put_int(1)
    b.put_int(4)
    b.put_str('foo')
    print repr(b.get_int())
    print repr(b.get_int())
    print repr(b.get_str())
