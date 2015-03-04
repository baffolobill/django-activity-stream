from __future__ import unicode_literals

import django
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _
from django.utils.encoding import python_2_unicode_compatible
from django.utils.timesince import timesince as djtimesince

try:
    from django.utils import timezone
    now = timezone.now
except ImportError:
    from datetime import datetime
    now = datetime.now

from mongoengine import fields, Document, CASCADE

from actstream import settings as actstream_settings
from actstream.managers import FollowQuerySet
from actstream.compat import user_model_label, get_user_model


@python_2_unicode_compatible
class Follow(Document):
    """
    Lets a user follow the activities of any specific actor
    """
    user = fields.ReferenceField(get_user_model(), reverse_delete_rule=CASCADE)
    follow_object = fields.GenericReferenceField(unique_with='user')
    actor_only = fields.BooleanField(
        verbose_name=_("Only follow actions where "
                        "the object is the target."),
        default=True)
    started = fields.DateTimeField(default=now)

    meta = {
        'indexes': [
            'user',
            'follow_object',
            'started',
        ],
        'queryset_class': FollowQuerySet,
    }

    def __str__(self):
        return '%s -> %s' % (self.user, self.follow_object)


@python_2_unicode_compatible
class Action(Document):
    """
    Action model describing the actor acting out a verb (on an optional
    target).
    Nomenclature based on http://activitystrea.ms/specs/atom/1.0/

    Generalized Format::

        <actor> <verb> <time>
        <actor> <verb> <target> <time>
        <actor> <verb> <action_object> <target> <time>

    Examples::

        <justquick> <reached level 60> <1 minute ago>
        <brosner> <commented on> <pinax/pinax> <2 hours ago>
        <washingtontimes> <started follow> <justquick> <8 minutes ago>
        <mitsuhiko> <closed> <issue 70> on <mitsuhiko/flask> <about 2 hours ago>

    Unicode Representation::

        justquick reached level 60 1 minute ago
        mitsuhiko closed issue 70 on mitsuhiko/flask 3 hours ago

    HTML Representation::

        <a href="http://oebfare.com/">brosner</a> commented on <a href="http://github.com/pinax/pinax">pinax/pinax</a> 2 hours ago

    """
    actor = fields.GenericReferenceField()

    verb = fields.StringField(max_length=255)
    description = fields.StringField(null=True)

    target = fields.GenericReferenceField(required=False, null=True)

    action_object = fields.GenericReferenceField(required=False, null=True)

    timestamp = fields.DateTimeField(default=now)

    public = fields.BooleanField(default=True)

    data = fields.DictField(required=False, null=True)

    meta = {
        'ordering': ['-timestamp'],
        'indexes': [
            '-timestamp',
            'verb',
            'actor',
            'target',
            'action_object',
            'public',
        ],
        'queryset_class': actstream_settings.get_action_manager()
    }

    def __str__(self):
        ctx = {
            'actor': self.actor,
            'verb': self.verb,
            'action_object': self.action_object,
            'target': self.target,
            'timesince': self.timesince()
        }
        if self.target:
            if self.action_object:
                return _('%(actor)s %(verb)s %(action_object)s on %(target)s %(timesince)s ago') % ctx
            return _('%(actor)s %(verb)s %(target)s %(timesince)s ago') % ctx
        if self.action_object:
            return _('%(actor)s %(verb)s %(action_object)s %(timesince)s ago') % ctx
        return _('%(actor)s %(verb)s %(timesince)s ago') % ctx

    def timesince(self, now=None):
        """
        Shortcut for the ``django.utils.timesince.timesince`` function of the
        current timestamp.
        """
        return djtimesince(self.timestamp, now).encode('utf8').replace(b'\xc2\xa0', b' ').decode('utf8')



# convenient accessors
actor_stream = Action.objects.actor
action_object_stream = Action.objects.action_object
target_stream = Action.objects.target
user_stream = Action.objects.user
document_stream = Action.objects.document_actions
any_stream = Action.objects.any
followers = Follow.objects.followers
following = Follow.objects.following


if django.VERSION[:2] < (1, 7):
    from actstream.apps import ActstreamConfig

    ActstreamConfig().ready()
