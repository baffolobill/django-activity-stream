from json import loads
from datetime import datetime
from inspect import getargspec
import struct
from time import time

from pymongo import MongoClient
import bson
from bson.errors import InvalidBSON
from pymongo.mongo_replica_set_client import MongoReplicaSetClient

from django.db import connection
from django.utils.six import text_type
from django.utils.timesince import timesince

from mongoengine.base import get_document
from mongoengine.django.auth import Group
from mongoengine.django.tests import MongoTestCase

from actstream.models import Action, Follow
from actstream.registry import register, unregister
from actstream.compat import get_user_model
from actstream.actions import follow
from actstream.signals import action


class LTE(int):
    def __new__(cls, n):
        obj = super(LTE, cls).__new__(cls, n)
        obj.n = n
        return obj

    def __eq__(self, other):
        return other <= self.n

    def __repr__(self):
        return "<= %s" % self.n


class MongoDumper(object):
    """
    @see: https://gist.github.com/8059155
    """
    def __init__(self, cls):
        self.cls = cls

    def install(self):
        self._used_msg_ids = []
        # save old methods
        orig_simple_command = [(k, v) for k, v in self.cls.__dict__.iteritems() if k.endswith('__simple_command')]
        self.orig_simple_command_func_name = orig_simple_command[0][0]
        self.orig_simple_command = orig_simple_command[0][1]
        self.orig_send_message = self.cls._send_message
        self.orig_send_message_with_response = self.cls._send_message_with_response

        # instrument methods to record messages
        self.cls._send_message = self._instrument(self.cls._send_message)
        self.cls._send_message_with_response = self._instrument(self.cls._send_message_with_response)
        setattr(self.cls, self.orig_simple_command_func_name,
                lambda *args, **kwargs: self._simple_command(*args, **kwargs))

    def uninstall(self):
        # remove instrumentation from pymongo
        self.cls._send_message = self.orig_send_message
        self.cls._send_message_with_response = self.orig_send_message_with_response

    def _simple_command(self, obj, sock_info, dbname, spec):
        response, time = self.orig_simple_command(obj, sock_info, dbname, spec)
        return response, time

    def _instrument(self, original_method):
        def instrumented_method(*args, **kwargs):
            message = _mongodb_decode_wire_protocol(args[1][1])
            if message['msg_id'] in self._used_msg_ids:
                return original_method(*args, **kwargs)
            self._used_msg_ids.append(message['msg_id'])
            start = time()
            result = original_method(*args, **kwargs)
            stop = time()
            duration = stop - start
            connection.queries.append({
                'mongo': message,
                'time': '%.3f' % duration,
            })
            return result
        return instrumented_method


MONGO_OPS = {
    2001: 'msg',
    2002: 'insert',
    2003: 'reserved',
    2004: 'query',
    2005: 'get_more',
    2006: 'delete',
    2007: 'kill_cursors',
}


def _mongodb_decode_wire_protocol(message):
    """ http://www.mongodb.org/display/DOCS/Mongo+Wire+Protocol """
    _, msg_id, _, opcode, _ = struct.unpack('<iiiii', message[:20])
    op = MONGO_OPS.get(opcode, 'unknown')
    zidx = 20
    collection_name_size = message[zidx:].find('\0')
    collection_name = message[zidx:zidx + collection_name_size]
    zidx += collection_name_size + 1
    skip, limit = struct.unpack('<ii', message[zidx:zidx + 8])
    zidx += 8
    try:
        msg = bson.decode_all(message[zidx:])
    except InvalidBSON:
        msg = 'invalid bson'
    return {'op': op, 'collection': collection_name,
            'msg_id': msg_id, 'skip': skip, 'limit': limit,
            'query': msg}


class ActivityBaseTestCase(MongoTestCase):
    actstream_models = ()
    maxDiff = None

    def setUp(self):
        self.dumpers = [MongoDumper(MongoClient), MongoDumper(MongoReplicaSetClient)]
        #for dumper in self.dumpers:
        #    dumper.install()

        self.User = get_user_model()
        self.User.drop_collection()
        register(self.User)
        for model in self.actstream_models:
            register(model)


    def assertSetEqual(self, l1, l2, msg=None, domap=True):
        if domap:
            l1 = map(text_type, l1)
        self.assertSequenceEqual(set(l1), set(l2), msg)

    def assertAllIn(self, bits, string):
        for bit in bits:
            self.assertIn(bit, string)

    def assertJSON(self, string):
        return loads(string)

    def tearDown(self):
        for model in self.actstream_models:
            model = get_document(model)
            unregister(model)
            model.drop_collection()
        Action.drop_collection()
        Follow.drop_collection()
        self.User.drop_collection()

        #for dumper in self.dumpers:
        #    dumper.uninstall()


class DataTestCase(ActivityBaseTestCase):
    actstream_models = ('auth.Group',)

    def setUp(self):
        self.testdate = datetime(2000, 1, 1)
        try:
            self.timesince = timesince(self.testdate).encode('utf8').replace(
                b'\xc2\xa0', b' ').decode()
        except UnicodeDecodeError:
            raise Exception(timesince(self.testdate).encode('utf8'))

        super(DataTestCase, self).setUp()
        self.group = Group.objects.create(name='CoolGroup')

        self.user1 = self.User.objects.create_superuser('admin@example.com', 'admin', first_name='John', last_name='Dow')
        self.user2 = self.User.objects.create_user('two@example.com', 'password', first_name='John Two', last_name='Dow')
        self.user3 = self.User.objects.create_user('three@example.com', 'password', first_name='John Three', last_name='Dow')
        # User1 joins group
        #self.user1.groups.add(self.group)
        self.join_action = action.send(self.user1, verb='joined',
                                       target=self.group,
                                       timestamp=self.testdate)[0][1]

        # User1 follows User2
        follow(self.user1, self.user2, timestamp=self.testdate)

        # User2 joins group
        #self.user2.groups.add(self.group)
        action.send(self.user2, verb='joined', target=self.group,
                    timestamp=self.testdate)

        # User2 follows group
        follow(self.user2, self.group, timestamp=self.testdate)

        # User1 comments on group
        # Use a site object here and predict the "__unicode__ method output"
        action.send(self.user1, verb='commented on', target=self.group,
                    timestamp=self.testdate)

        # User 3 did something but doesn't following someone
        action.send(self.user3, verb='liked actstream', timestamp=self.testdate)
