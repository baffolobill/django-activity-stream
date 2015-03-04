from mongoengine.base import get_document
from mongoengine.queryset import QuerySet, Q

from actstream.decorators import stream
from actstream.registry import check


class ActionQuerySet(QuerySet):
    """
    Default manager for Actions, accessed through Action.objects
    """

    def public(self, *args, **kwargs):
        """
        Only return public actions
        """
        kwargs['public'] = True
        return self.filter(*args, **kwargs)

    @stream
    def actor(self, obj, **kwargs):
        """
        Stream of most recent actions where obj is the actor.
        Keyword arguments will be passed to Action.objects.filter
        """
        check(obj)
        return obj.actor_actions.public(**kwargs)

    @stream
    def target(self, obj, **kwargs):
        """
        Stream of most recent actions where obj is the target.
        Keyword arguments will be passed to Action.objects.filter
        """
        check(obj)
        return obj.target_actions.public(**kwargs)

    @stream
    def action_object(self, obj, **kwargs):
        """
        Stream of most recent actions where obj is the action_object.
        Keyword arguments will be passed to Action.objects.filter
        """
        check(obj)
        return obj.action_object_actions.public(**kwargs)

    @stream
    def document_actions(self, document, **kwargs):
        """
        Stream of most recent actions by any particular document
        """
        check(document)
        if hasattr(document, '__name__'):
            doc_cls_name = document.__name__
        else:
            doc_cls_name = document.__class__.__name__

        return self.public(
            (Q(__raw__={'target._cls': doc_cls_name}) |
             Q(__raw__={'action_object._cls': doc_cls_name}) |
             Q(__raw__={'actor._cls': doc_cls_name})),
            **kwargs
        )

    @stream
    def any(self, obj, **kwargs):
        """
        Stream of most recent actions where obj is the actor OR target OR action_object.
        """
        check(obj)
        return self.public(
            Q(
                actor=obj
            ) | Q(
                target=obj
            ) | Q(
                action_object=obj
            ), **kwargs)

    @stream
    def user(self, obj, **kwargs):
        """
        Stream of most recent actions by objects that the passed User obj is
        following.
        """
        q = Q()
        qs = self.public()

        if not obj:
            return qs.none()

        check(obj)
        actors = []
        others = []

        if kwargs.pop('with_user_activity', False):
            actors.append(obj)

        follow_objects = get_document('actstream.Follow').objects.filter(
            user=obj).values_list('follow_object', 'actor_only').no_cache()

        for follow_object, actor_only in follow_objects():
            actors.append(follow_object)
            if not actor_only:
                others.append(follow_object)

        if len(actors) + len(others) == 0:
            return qs.none()

        if len(actors):
            q = q | Q(actor__in=actors)

        if len(others):
            q = q | Q(target__in=others) | Q(action_object__in=others)

        return qs.filter(q, **kwargs)


class FollowQuerySet(QuerySet):
    """
    Manager for Follow document.
    """

    def for_object(self, instance):
        """
        Filter to a specific instance.
        """
        check(instance)
        return self.filter(follow_object=instance)

    def is_following(self, user, instance):
        """
        Check if a user is following an instance.
        """
        if not user or user.is_anonymous():
            return False
        queryset = self.for_object(instance)
        return bool(queryset.filter(user=user).count())

    def followers_qs(self, actor):
        """
        Returns a queryset of User objects who are following the given actor (eg my followers).
        """
        check(actor)
        return self.for_object(actor).select_related()

    def followers(self, actor):
        """
        Returns a list of User objects who are following the given actor (eg my followers).
        """
        return [follow.user for follow in self.followers_qs(actor)]

    def following_qs(self, user, *documents):
        """
        Returns a queryset of actors that the given user is following (eg who im following).
        Items in the list can be of any document unless a list of restricted models are passed.
        Eg following(user, User) will only return users following the given user

        TEST REQUIRED for __raw__ query
        """
        qs = self.filter(user=user)
        ctype_filters = Q()
        for document in documents:
            check(document)
            ctype_filters |= Q(__raw__={'follow_object._cls': document.__name__})
        qs = qs.filter(ctype_filters)
        return qs.select_related()

    def following(self, user, *documents):
        """
        Returns a list of actors that the given user is following (eg who im following).
        Items in the list can be of any document unless a list of restricted models are passed.
        Eg following(user, User) will only return users following the given user
        """
        return [follow.follow_object for follow in self.following_qs(user, *documents)]
