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

class DiligentWorker(threading.Thread):
	lock = threading.Lock()

	def __init__(self, x):
		threading.Thread.__init__(self)
		self.x = x
	
	def run(self):
		val = create_and_calc(self.x)
		DiligentWorker.lock.acquire()
		CACHE[str(self.x)] = val
		DiligentWorker.lock.release()

workingAt = {}
worker = []
@app.route('/diligent/<int:x>')
def diligent_service(x):
	def thread_filter(x):
		x.join(0.001)
		return x.isAlive()

	xs = str(x)
	if xs in CACHE:
		val = CACHE[xs]
		global worker
		worker = filter(thread_filter, worker)
		for n in (x+1, x+2):
			if not n in workingAt:
				w = DiligentWorker(n)
				worker.append(w)
				workingAt[n] = w
				w.start()
		return val
	elif x in workingAt:
		worker = workingAt[x]
		worker.join()
		return CACHE[xs]
	else:
		val = create_and_calc(x)
		CACHE[xs] = val
		return val

@app.route('/clear')
def clear_cache():
	return str(CACHE.flush_all())
	
if __name__ == '__main__':
	port = int(os.environ.get('PORT', 5000))
	app.run(host='0.0.0.0', port=port)

