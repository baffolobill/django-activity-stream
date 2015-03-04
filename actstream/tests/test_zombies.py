from random import choice

from django.conf import settings
from django.db import connection
from django.utils.six import text_type

from actstream.compat import get_user_model
from actstream.signals import action
from actstream.models import document_stream
from .base import ActivityBaseTestCase


class ZombieTest(ActivityBaseTestCase):
    """
    Does not work properly. I didn't find any built-in
    to calculate queries number. Current solution returns
    zero new queries for queryset. It seems pymongo and/or
    mongoengine are cached them somehow and do not extra queries.
    """
    human = 10
    zombie = 1

    def setUp(self):
        self.User = get_user_model()
        super(ZombieTest, self).setUp()
        settings.DEBUG = True

        player_generator = lambda n, count: [self.User.objects.create(
            email='%s%d@exa.com' % (n, i), page_url='%s%d' % (n, i)) for i in range(count)]

        self.humans = player_generator('human', self.human)
        self.zombies = player_generator('zombie', self.zombie)

        self.zombie_apocalypse()

    def tearDown(self):
        settings.DEBUG = False
        super(ZombieTest, self).tearDown()

    def zombie_apocalypse(self):
        humans = self.humans[:]
        zombies = self.zombies[:]
        while humans:
            for z in self.zombies:
                victim = choice(humans)
                humans.remove(victim)
                zombies.append(victim)
                action.send(z, verb='killed', target=victim)
                if not humans:
                    break

    def check_query_count(self, queryset):
        for dumper in self.dumpers:
            dumper.install()

        ci = len(connection.queries)
        result = list([map(text_type, (x.actor, x.target, x.action_object))
                       for x in queryset])

        self.assertTrue(len(connection.queries) - ci <= 4,
                        'Too many queries, got %d expected no more than 4' %
                        len(connection.queries))

        for dumper in self.dumpers:
            dumper.uninstall()

        return result

    def test_query_count(self):
        queryset = document_stream(self.User)
        result = self.check_query_count(queryset)
        self.assertEqual(len(result), 10)

    def test_query_count_sliced(self):
        queryset = document_stream(self.User)[:5]
        result = self.check_query_count(queryset)
        self.assertEqual(len(result), 5)

