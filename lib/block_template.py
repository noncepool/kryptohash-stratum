import StringIO
import binascii
import struct

import util
import merkletree
import halfnode
from coinbasetx import CoinbaseTransaction
import lib.logger
log = lib.logger.get_logger('block_template')

import settings

class BlockTemplate(halfnode.CBlock):
    '''Template is used for generating new jobs for clients.
    Let's iterate extranonce1, extranonce2, ntime and nonce
    to find out valid coin block!'''
    
    coinbase_transaction_class = CoinbaseTransaction
    
    def __init__(self, timestamper, coinbaser, job_id):
        super(BlockTemplate, self).__init__()
        
        self.job_id = job_id 
        self.timestamper = timestamper
        self.coinbaser = coinbaser
        
        self.prevhash_bin = '' # reversed binary form of prevhash
        self.prevhash_hex = ''
        self.timedelta = 0
        self.curtime = 0
        self.target = 0
        self.merkletree = None
        self.blank_hash = '00000000000000000000000000000000000000000000000000000000000000000000000000000000'
                
        self.broadcast_args = []
        self.submits = [] 
                
    def fill_from_rpc(self, data):
        '''Convert getblocktemplate result into BlockTemplate instance'''
        if 'height' not in data:
            log.info("Waiting for new work...")
            self.prevhash_hex = self.blank_hash 
            self.broadcast_args = self.build_fake_broadcast_args()
            return

        txhashes = [None] + [ util.ser_uint320(int(t['hash'], 16)) for t in data['transactions'] ]
        mt = merkletree.MerkleTree(txhashes)

        self.height = data['height']
        self.nVersion = data['version']
        self.hashPrevBlock = int(data['previousblockhash'], 16)
        self.nBits = int(data['bits'], 16)
        self.nBitsHex = data['bits']

        self.hashMerkleRoot = 0
        self.nTime = 0
        self.nNonce = 0
        self.cbTxTime = int(self.timestamper.time())
        self.nTxTime = self.cbTxTime * 1000
        self.nHashCoin = 0 
        self.sigchecksum = 0

        coinbase = CoinbaseTransaction(self.timestamper, self.coinbaser, data['coinbasevalue'], data['coinbaseaux']['flags'], 
            data['height'], settings.COINBASE_EXTRAS, self.cbTxTime)

        self.vtx = [ coinbase, ]
        for tx in data['transactions']:
            t = halfnode.CTransaction()
            t.deserialize(StringIO.StringIO(binascii.unhexlify(tx['data'])))
            self.vtx.append(t)
            
        self.curtime = data['curtime']
        self.timedelta = self.curtime - int(self.timestamper.time()) 
        self.merkletree = mt
        self.target = int((data['target']), 16)
        log.info("Block height: %i network difficulty: %s" % (self.height, self.diff_to_t(self.target)))

        # Reversed prevhash
        #self.prevhash_bin = binascii.unhexlify(util.reverse_hash_80(data['previousblockhash']))
        self.prevhash_bin = binascii.unhexlify(util.rev(data['previousblockhash']))
        self.prevhash_hex = "%080x" % self.hashPrevBlock
        #log.info("%s\n", repr(self))
        
        self.broadcast_args = self.build_broadcast_args()

    def diff_to_t(self, difficulty):
        '''Converts difficulty to target'''
        diff1 = 0x000000ffff000000000000000000000000000000000000000000000000000000000000000000000
        return float(diff1 * 16) / float(difficulty)
                
    def register_submit(self, extranonce1, extranonce2, ntime, nonce):
        t = (extranonce1, extranonce2, ntime, nonce)
        if t not in self.submits:
            self.submits.append(t)
            return True
        return False

    def build_fake_broadcast_args(self):
        job_id = '00'
        prevhash = self.blank_hash
        (coinb1, coinb2) = ([self.blank_hash],[self.blank_hash])
        merkle_branch = [self.blank_hash]
        version = binascii.hexlify(struct.pack("<i", 0))
        nbits = binascii.hexlify(struct.pack("<I", 0))
        ntime = binascii.hexlify(struct.pack("<I", 0))
        nTxTime = binascii.hexlify(struct.pack("<Q", 0))
        clean_jobs = True
          
        return (job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, nTxTime, clean_jobs)

    def build_broadcast_args(self):
        job_id = self.job_id
        prevhash = binascii.hexlify(self.prevhash_bin)
        (coinb1, coinb2) = [ binascii.hexlify(x) for x in self.vtx[0]._serialized ]
        merkle_branch = [ binascii.hexlify(x) for x in self.merkletree._steps ]
        version = binascii.hexlify(struct.pack("<i", self.nVersion))
        nbits = binascii.hexlify(struct.pack("<I", self.nBits))
        ntime = binascii.hexlify(struct.pack("<I", self.curtime))
        nTxTime = binascii.hexlify(struct.pack("<Q", self.nTxTime))
        clean_jobs = True
        
        return (job_id, prevhash, coinb1, coinb2, merkle_branch, version, nbits, ntime, nTxTime, clean_jobs)

    def serialize_coinbase(self, extranonce1, extranonce2):
        '''Serialize coinbase with given extranonce1 and extranonce2
        in binary form'''
        (part1, part2) = self.vtx[0]._serialized
        return part1 + extranonce1 + extranonce2 + part2
    
    def check_ntime(self, ntime):
        '''Check for ntime restrictions.'''
        if ntime < self.curtime:
            return False        
        if ntime > (self.timestamper.time() + 7200):
            # Be strict on ntime into the near future
            # may be unnecessary
            return False        
        return True

    def serialize_header(self, merkle_root_int, ntime_bin, nonce_bin):
        r = struct.pack("<i", self.nVersion)
        r += struct.pack("<i", self.nRegion)
        r += self.prevhash_bin
        r += merkle_root_int
        r += struct.pack("<Q", self.nTxTime)
        r += struct.pack("<Q", self.nHashCoin)
        r += struct.pack("<I", self.sigchecksum)
        r += struct.pack("<I", self.nBits)
        r += struct.pack("<I", ntime_bin)
        r += struct.pack("<I", nonce_bin)
        return r   

    def finalize(self, merkle_root_int, extranonce1_bin, extranonce2_bin, ntime, nonce):       
        self.hashMerkleRoot = merkle_root_int
        self.nTime = ntime
        self.nNonce = nonce
        self.vtx[0].set_extranonce(extranonce1_bin + extranonce2_bin)        
        self.powhash320 = None      

