import os
from sys import argv
import logging
from multiprocessing import Queue, Process

import zmq
import msgpack
from pyramid.paster import get_appsettings

N_PROCESSES = 4
SENTINEL = 'XXX'

#logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

# config
logging.info('Loading configuration')
ZMQ_URI = "tcp://0.0.0.0:5001"
settings = get_appsettings(argv[1], 'triage')

# zero mq
logging.info('Initializing zeromq socket at: ' + ZMQ_URI)
context = zmq.Context()
socket = context.socket(zmq.SUB)
socket.bind(ZMQ_URI)
socket.setsockopt(zmq.SUBSCRIBE, '')

class MongoConsumer(Process):
    def __init__(self, queue):
        self.queue = queue
        self.conn = None
        super(MongoConsumer, self).__init__()

    def run(self):
        import mongoengine
        from models import Error
        while True:
            # mongo
            logging.info('Process %d connecting to mongo at: mongodb://' % os.getpid() + settings['mongodb.host'] + '/' + settings['mongodb.db_name'])
            mongoengine.connect(settings['mongodb.db_name'], host=settings['mongodb.host'])

            msg = self.queue.get()
            if msg == SENTINEL:
                break

            try:
                if type(msg) == dict:
                    logging.debug('found object in message')
                    error = Error.create_from_msg(msg)
                    error.save()
                    logging.debug('saved error')
            except Exception:
                logging.exception('Failed to process error')

# messagepack
unpacker = msgpack.Unpacker()

queue = Queue()
pool = [MongoConsumer(queue) for i in xrange(N_PROCESSES)]

for p in pool:
    p.start()

# serve!
logging.info('Serving!')
try:
    while True:
        try:
            data = socket.recv()
            logging.debug('received data')
            unpacker.feed(data)
            logging.debug('fed data to unpacker')
            for msg in unpacker:
                logging.debug('queuing message from unpacker')
                queue.put(msg)
        except Exception:
            logging.exception('Failed to unpack error')

except KeyboardInterrupt:
    logging.info('Shutting down...')
    # wait for the processes to end
    for p in pool:
        queue.put(SENTINEL)
    for p in pool:
        p.wait()

