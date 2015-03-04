# -*- coding: utf-8  -*-

#from django.contrib.auth.models import Group

from django.utils.translation import ugettext_lazy as _
from django.utils.translation import activate, get_language
from django.utils.six import text_type
#from django.core.urlresolvers import reverse

from mongoengine.django.auth import Group

from actstream.models import (Action, Follow, document_stream, user_stream,
                              actor_stream, following, followers)
from actstream.actions import follow, unfollow
from actstream.signals import action
from .base import DataTestCase


class ActivityTestCase(DataTestCase):

    def test_aauser1(self):
        self.assertSetEqual(self.user1.actor_actions.all(), [
            'John Dow commented on CoolGroup %s ago' % self.timesince,
            'John Dow started following John Two Dow %s ago' % self.timesince,
            'John Dow joined CoolGroup %s ago' % self.timesince,
        ])

    def test_user2(self):
        self.assertSetEqual(actor_stream(self.user2), [
            'John Two Dow started following CoolGroup %s ago' % self.timesince,
            'John Two Dow joined CoolGroup %s ago' % self.timesince,
        ])

    def test_group(self):
        self.assertEqual(True, True)
        if False:
            self.assertSetEqual(actor_stream(self.group),
                                ['CoolGroup responded to John Dow: Sweet Group!... '
                                 '%s ago' % self.timesince])

    def test_following(self):
        self.assertEqual(list(following(self.user1)), [self.user2])
        self.assertEqual(len(following(self.user2, self.User)), 0)

    def test_followers(self):
        self.assertEqual(list(followers(self.group)), [self.user2])

    def test_empty_follow_stream(self):
        unfollow(self.user1, self.user2)
        self.assertFalse(bool(len(user_stream(self.user1))))

        self.assertSetEqual(
            user_stream(self.user3, with_user_activity=True),
            ['John Three Dow liked actstream %s ago' % self.timesince]
        )

    def test_stream(self):
        self.assertSetEqual(user_stream(self.user1), [
            'John Two Dow started following CoolGroup %s ago' % self.timesince,
            'John Two Dow joined CoolGroup %s ago' % self.timesince,
        ])

    def test_stream_stale_follows(self):
        """
        user_stream() should ignore Follow objects with stale actor
        references.
        """
        self.user2.delete()
        self.assertNotIn('Two', str(user_stream(self.user1)))

    def test_doesnt_generate_duplicate_follow_records(self):
        g = Group.objects.get_or_create(name='DupGroup')[0]
        s = self.User.objects.get_or_create(email='dupuser@example.com', first_name='dup', last_name='user')[0]

        f1 = follow(s, g)
        self.assertTrue(f1 is not None, "Should have received a new follow "
                                        "record")
        self.assertTrue(isinstance(f1, Follow), "Returns a Follow object")

        follows = Follow.objects.filter(user=s, follow_object=g)
        self.assertEqual(1, follows.count(),
                         "Should only have 1 follow record here")

        f2 = follow(s, g)
        follows = Follow.objects.filter(user=s, follow_object=g)
        self.assertEqual(1, follows.count(),
                         "Should still only have 1 follow record here")
        self.assertTrue(f2 is not None, "Should have received a Follow object")
        self.assertTrue(isinstance(f2, Follow), "Returns a Follow object")
        self.assertEqual(f1, f2, "Should have received the same Follow "
                                 "object that I first submitted")

    def test_following_models_OR_query(self):
        follow(self.user1, self.group, timestamp=self.testdate)
        self.assertSetEqual([self.user2, self.group],
                            following(self.user1, Group, self.User), domap=False)

    def test_y_no_orphaned_follows(self):
        follows = Follow.objects.count()
        self.user2.delete()
        self.assertEqual(follows - 1, Follow.objects.count())

    def test_z_no_orphaned_actions(self):
        actions = self.user1.actor_actions.count()
        self.user2.delete()
        self.assertEqual(actions - 1, self.user1.actor_actions.count())

    def test_generic_relation_accessors(self):
        self.assertEqual(self.user2.actor_actions.count(), 2)
        self.assertEqual(self.user2.target_actions.count(), 1)
        self.assertEqual(self.user2.action_object_actions.count(), 0)

    def test_hidden_action(self):
        testaction = self.user1.actor_actions.all()[0]
        testaction.public = False
        testaction.save()
        self.assertNotIn(testaction, self.user1.actor_actions.public())

    def test_model_actions_with_kwargs(self):
        """
        Testing the model_actions method of the ActionManager
        by passing kwargs
        """
        self.assertSetEqual(document_stream(self.user1, verb='commented on'), [
            'John Dow commented on CoolGroup %s ago' % self.timesince,
        ])

    def test_user_stream_with_kwargs(self):
        """
        Testing the user method of the ActionManager by passing additional
        filters in kwargs
        """
        self.assertSetEqual(user_stream(self.user1, verb='joined'), [
            'John Two Dow joined CoolGroup %s ago' % self.timesince,
        ])

    def test_none_returns_an_empty_queryset(self):
        qs = Action.objects.none()
        self.assertEqual(qs.count(), 0)

    def test_with_user_activity(self):
        self.assertNotIn(self.join_action, list(user_stream(self.user1)))
        self.assertIn(self.join_action,
                      list(user_stream(self.user1, with_user_activity=True)))
