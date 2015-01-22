#!/usr/bin/python
# Public Domain
# Original author: ArtForz
# Twisted integration: slush

import struct
import socket
import binascii
import time
import sys
import random
import cStringIO

from twisted.internet.protocol import Protocol
from util import *
import settings

import kshake320_hash

import lib.logger
log = lib.logger.get_logger('halfnode')

MY_VERSION = 1
MY_SUBVERSION = ".7"

class COutPoint(object):
    def __init__(self):
        self.hash = 0
        self.n = 0
    def deserialize(self, f):
        self.hash = deser_uint320(f)
        self.n = struct.unpack("<I", f.read(4))[0]
    def serialize(self):
        r = ""
        r += ser_uint320(self.hash)
        r += struct.pack("<I", self.n)
        return r
    def __repr__(self):
        return "COutPoint(hash=%080x n=%i)" % (self.hash, self.n)

class CTxIn(object):
    def __init__(self):
        self.prevout = COutPoint()
        self.scriptSig = ""
        self.nSequence = 0
    def deserialize(self, f):
        self.prevout = COutPoint()
        self.prevout.deserialize(f)
        self.scriptSig = deser_string(f)
        self.nSequence = struct.unpack("<I", f.read(4))[0]
    def serialize(self):
        r = ""
        r += self.prevout.serialize()
        r += ser_string(self.scriptSig)
        r += struct.pack("<I", self.nSequence)
        return r
    def __repr__(self):
        return "CTxIn(prevout=%s scriptSig=%s nSequence=%i)" % (repr(self.prevout), binascii.hexlify(self.scriptSig), self.nSequence)

class CTxOut(object):
    def __init__(self):
        self.nValue = 0
        self.scriptPubKey = ""
    def deserialize(self, f):
        self.nValue = struct.unpack("<q", f.read(8))[0]
        self.scriptPubKey = deser_string(f)
    def serialize(self):
        r = ""
        r += struct.pack("<q", self.nValue)
        r += ser_string(self.scriptPubKey)
        return r
    def __repr__(self):
        return "CTxOut(nValue=%i.%08i scriptPubKey=%s)" % (self.nValue // 100000, self.nValue % 100000, binascii.hexlify(self.scriptPubKey))

class CTransaction(object):
    def __init__(self):
            self.nVersion = 2
            self.vin = []
            self.vout = []
            self.ntxTime = 0
            self.nLockTime = 0
            self.nHashCoin = 0
            self.hash320 = None

    def deserialize(self, f):
            self.nVersion = struct.unpack("<i", f.read(4))[0]
            self.vin = deser_vector(f, CTxIn)
            self.vout = deser_vector(f, CTxOut)
            self.ntxTime = struct.unpack("<Q", f.read(8))[0]
            self.nLockTime = struct.unpack("<Q", f.read(8))[0]
            self.nHashCoin = struct.unpack("<Q", f.read(8))[0]
            self.hash320 = None

    def serialize(self):
            r = ""
            r += struct.pack("<i", self.nVersion)
            r += ser_vector(self.vin)
            r += ser_vector(self.vout)
            r += struct.pack("<Q", self.ntxTime)
            r += struct.pack("<Q", self.nLockTime)
            r += struct.pack("<Q", self.nHashCoin)
            return r
 
    def calc_hash320(self):
        if self.hash320 is None: 
            self.hash320 = uint320_from_str(kshake320_hash.getHash320(self.serialize()))
        return self.hash320
    
    def is_valid(self):
        self.calc_hash320()
        for tout in self.vout:
            if tout.nValue < 0 or tout.nValue > 21000000L * 100000000L:
                return False
        return True
    def __repr__(self):
        return "CTransaction(nVersion=%i vin=%s vout=%s ntxTime=%s nLockTime=%i nHashCoin=%i)" % (self.nVersion, repr(self.vin), repr(self.vout), self.ntxTime, self.nLockTime, self.nHashCoin)

class CBlock(object):
    def __init__(self):
        self.nVersion = 1
        self.nRegion = 0
        self.hashPrevBlock = 0
        self.hashMerkleRoot = 0
        self.nTxTime = 0
        self.nHashCoin = 0 
        self.sigchecksum = 0
        self.nBits = 0
        self.nTime = 0
        self.nNonce = 0
        self.vtx = []
        self.powhash320 = None

    def deserialize(self, f):
        self.nVersion = struct.unpack("<i", f.read(4))[0]
        self.nRegion = struct.unpack("<i", f.read(4))[0]
        self.hashPrevBlock = deser_uint320(f)
        self.hashMerkleRoot = deser_uint320(f)
        self.nTxTime = struct.unpack("<Q", f.read(8))[0]
        self.nHashCoin = struct.unpack("<Q", f.read(8))[0]
        self.sigchecksum = struct.unpack("<I", f.read(4))[0]
        self.nBits = struct.unpack("<I", f.read(4))[0]
        self.nTime = struct.unpack("<I", f.read(4))[0]
        self.nNonce = struct.unpack("<I", f.read(4))[0]
        self.vtx = deser_vector(f, CTransaction)

    def serialize(self):
        r = []
        r.append(struct.pack("<i", self.nVersion))
        r.append(struct.pack("<i", self.nRegion))
        r.append(ser_uint320(self.hashPrevBlock))
        r.append(ser_uint320(self.hashMerkleRoot))
        r.append(struct.pack("<Q", self.nTxTime))
        r.append(struct.pack("<Q", self.nHashCoin))
        r.append(struct.pack("<I", self.sigchecksum))
        r.append(struct.pack("<I", self.nBits))
        r.append(struct.pack("<I", self.nTime))
        r.append(struct.pack("<I", self.nNonce))
        r.append(ser_vector(self.vtx))
        return ''.join(r)

    def calc_powhash320(self):
        if self.powhash320 is None:
            r = []
            r.append(struct.pack("<i", self.nVersion))
            r.append(struct.pack("<i", self.nRegion))
            r.append(ser_uint320(self.hashPrevBlock))
            r.append(ser_uint320(self.hashMerkleRoot))
            r.append(struct.pack("<Q", self.nTxTime))
            r.append(struct.pack("<Q", self.nHashCoin))
            r.append(struct.pack("<I", self.sigchecksum))
            r.append(struct.pack("<I", self.nBits))
            r.append(struct.pack("<I", self.nTime))
            r.append(struct.pack("<I", self.nNonce))
            self.powhash320 = uint320_from_str(kshake320_hash.getPoWHash(''.join(r)))
        return self.powhash320

    def is_valid(self):
        self.calc_powhash320()
        #target = self.nBits
        target = self.target

        if self.powhash320 > target:
                return False

        hashes = []
        for tx in self.vtx:
            tx.hash320 = None
            if not tx.is_valid():
                return False
            tx.calc_hash320()
            hashes.append(ser_uint320(tx.hash320))
        
        while len(hashes) > 1:
            newhashes = []
            for i in xrange(0, len(hashes), 2):
                i2 = min(i+1, len(hashes)-1)
                newhashes.append(kshake320_hash.getHash320(hashes[i] + hashes[i2]))
            hashes = newhashes
        
        if uint320_from_str(hashes[0]) != self.hashMerkleRoot:
            return False
        return True
    def __repr__(self):
        return "CBlock(nVersion=%i nRegion=%i hashPrevBlock=%080x hashMerkleRoot=%080x nTxTime=%i nTime=%s nHashCoin=%i sigchecksum=%i nBits=%08x nNonce=%08x vtx=%s)" % (self.nVersion, self.nRegion, self.hashPrevBlock, self.hashMerkleRoot, self.nTxTime, time.ctime(self.nTime), self.nHashCoin, self.sigchecksum, self.nBits, self.nNonce, repr(self.vtx))


