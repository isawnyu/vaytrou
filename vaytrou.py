import logging
import os

from repoze.zodbconn.finder import PersistentApplicationFinder
from rtree import Rtree
from simplejson import dumps, loads
import tornado.httpserver
import tornado.ioloop
from tornado.options import define, options
from tornado.options import parse_config_file, parse_command_line
import tornado.web

from indexing import BatchError, ChangeSet, ConflictError
from vrtree import VRtreeIndex

def appmaker(root):
    if not 'index' in root:
        index = VRtreeIndex()
        root['index'] = index
        import transaction
        transaction.commit()
    return root['index']

index = None

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write('index has %s items\n' % len(index.bwd))
    def post(self):
        try:
            data = loads(self.request.body)
            changeset = ChangeSet(
                additions=data.get('index'), deletions=data.get('unindex'))
            index.batch(changeset)
            self.set_status(200)
            self.set_header('content-type', 'application/json')
            self.write(dumps(dict(msg='Batch success')))
        except (BatchError, ConflictError) as error:
            self.set_status(409)
            self.set_header('content-type', 'application/json')
            self.write(dumps(dict(msg=str(error))))
        except:            
            raise

class IntersectionHandler(tornado.web.RequestHandler):
    def get(self):
        '''Perform intersection search'''
        try:
            bbox = self.get_argument('bbox')
            coords = tuple(float(x) for x in bbox.split(','))
            results = list(index.intersection(coords))
            self.set_status(200)
            self.set_header('content-type', 'application/json')
            self.write(dumps(dict(items=results)))
        except:
            raise

class NearestHandler(tornado.web.RequestHandler):
    def get(self):
        '''Perform intersection search'''
        try:
            bbox = self.get_argument('bbox')
            coords = tuple(float(x) for x in bbox.split(','))
            limit = int(self.get_argument('limit', '1'))
            results = list(index.nearest(coords, limit))
            self.set_status(200)
            self.set_header('content-type', 'application/json')
            self.write(dumps(dict(items=results)))
        except:
            raise

class BatchHandler(tornado.web.RequestHandler):
    def post(self):
        try:
            data = loads(self.request.body)
            index.batch(additions=data['index'], deletions=data['unindex'])
            self.set_status(200)
            self.set_header('content-type', 'application/json')
            self.write(dumps(dict(msg='Batch success')))
        except BatchError as error:
            self.set_status(409)
            self.set_header('content-type', 'application/json')
            self.write(dumps(dict(msg=str(error))))
        except:            
            raise
            
application = tornado.web.Application([
    (r'/', MainHandler),
    (r'/intersection', IntersectionHandler),
    (r'/nearest', NearestHandler),
])

define('data_directory', default=None, help='Data storage directory')
define('index_name', default='v1', help='R-tree index name')

# TODO: above goes into a module, below into a script for which we properly
# manage egg paths

if __name__ == '__main__':
    parse_config_file('etc/server.conf')
    parse_command_line()
    finder = PersistentApplicationFinder(
        'file://%s/Data.fs' % options.data_directory, appmaker)
    environ = {}
    index = finder(environ)
    index.fwd = Rtree('%s/%s' % (options.data_directory, options.index_name))
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(8888)
    try:
        loop = tornado.ioloop.IOLoop.instance()
        loop.start()
    except KeyboardInterrupt:
        loop.stop()
        print 'Exiting.'
    finally:
        index.fwd.close()
