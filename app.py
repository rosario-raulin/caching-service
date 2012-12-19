import os
import flask
import math
import random
import string
import hmac
import hashlib
import zipfile
import pylibmc
import threading
import time

app = flask.Flask(__name__)
app.debug = True

ALPHABET = string.letters + string.digits
BLOCKSIZE = 1024 * 1024 * 4
KEY = "foobar"

CACHE = pylibmc.Client(
    servers=[os.environ.get('MEMCACHE_SERVERS')],
	username=os.environ.get('MEMCACHE_USERNAME'),
	password=os.environ.get('MEMCACHE_PASSWORD'),
	binary=True
)

def gen_random_file(path, size):
	rand = ''.join([random.choice(ALPHABET) for i in range(0, BLOCKSIZE)])
	blocks = int(math.ceil(size / BLOCKSIZE))
	with zipfile.ZipFile(path, 'w') as myzip:
		for i in range(0, blocks):
			myzip.writestr('zip%d.txt' % i, rand)
		rest = size - blocks * BLOCKSIZE
		if rest > 0:
			myzip.writestr('zip.txt', rand[0:size - blocks * BLOCKSIZE])

def calc_hmac(path):
	gen = hmac.new(KEY, digestmod=hashlib.sha256)
	with open(path, 'r') as f:
		for nextBlock in iter(lambda: f.read(BLOCKSIZE), ''):
			gen.update(nextBlock)
	return gen.digest()

def is_last_byte_even(inp):
	array = bytearray(inp)
	return array[len(array) - 1] % 2 == 0

def create_and_calc(x):
	fname = '/tmp/foo%d-%f.zip' % (x, time.time())
	gen_random_file(fname, x * 1024 * 1024)
	return str(is_last_byte_even(calc_hmac(fname)))

class DiligentWorker(threading.Thread):
	lock = threading.Lock()

	def __init__(self, x):
		threading.Thread.__init__(self)
		self.x = x
		self.xs = str(x)
		
	def run(self):
		if not self.xs in CACHE:
			value = create_and_calc(self.x)
			DiligentWorker.lock.acquire()
			CACHE[self.xs] = value
			DiligentWorker.lock.release()

@app.route('/<int:x>')
def service(x):
	return create_and_calc(x)

@app.route('/cache/<int:x>')
def cache_service(x, negative = False):
	xs = str(x)
	if xs in CACHE:
		return CACHE[xs]
	else:
		val = create_and_calc(x)
		if (negative or val == "True"):
			CACHE[xs] = val
		return val

@app.route('/negative/<int:x>')
def negative_service(x):
	return cache_service(x, True)

THREADS = []

@app.route('/diligent/<int:x>')
def diligent_service(x):

	global THREADS
	ts = []
	for thread in THREADS:
		thread.join(0.001)
		if thread.isAlive():
			ts.append(thread)
	print ts
	THREADS = ts
	print THREADS

	xs = str(x)
	if xs in CACHE:
		val = CACHE[xs]
		w1 = DiligentWorker(x + 1)
		w2 = DiligentWorker(x - 1)
		THREADS.append(w1)
		THREADS.append(w2)
		w1.start()
		w2.start()
		return val
	else:
		value = create_and_calc(x)
		CACHE[xs] = value
		return value

@app.route('/clear')
def clear_cache():
	return str(CACHE.flush_all())
	
if __name__ == '__main__':
	port = int(os.environ.get('PORT', 5000))
	app.run(host='0.0.0.0', port=port)

