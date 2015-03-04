from functools import wraps
from inspect import isclass
import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.six import string_types


from mongoengine.base import get_document, TopLevelDocumentMetaclass
from mongoengine.queryset import Q
from mongoengine.signals import pre_delete

class RegistrationError(Exception):
    pass

def actor_actions(self):
    Action = get_document('actstream.Action')
    return Action.objects(actor=self)

def target_actions(self):
    Action = get_document('actstream.Action')
    return Action.objects(target=self)

def action_object_actions(self):
    Action = get_document('actstream.Action')
    return Action.objects(action_object=self)

def clear_relations_on_delete(sender, document):
    Action = get_document('actstream.Action')
    Action.objects(Q(actor=document) | Q(target=document) | Q(action_object=document)).delete()

def setup_generic_relations(document_class):
    """
    Set up GenericRelations for actionable models.
    """

    document_class.actor_actions = property(actor_actions)
    document_class.target_actions = property(target_actions)
    document_class.action_object_actions = property(action_object_actions)

    pre_delete.connect(clear_relations_on_delete, sender=document_class)

    relations = {}
    for field in ('actor', 'target', 'action_object'):
        attr = '%s_actions' % field

        relations[field] = getattr(document_class, attr)

    return relations


def is_installed(document_class):
    """
    Returns True if a document_class is installed.
    """
    return re.sub(r'\.models.*$', '', document_class.__module__) in settings.INSTALLED_APPS


def validate(document_class, exception_class=ImproperlyConfigured):
    if isinstance(document_class, string_types):
        document_class = get_document(document_class)

    if not isinstance(document_class, TopLevelDocumentMetaclass):
        raise exception_class(
            'Object %r is not a Document class.' % document_class)
    if document_class._meta.get('abstract', False):
        raise exception_class(
            'The document %r is abstract, so it cannot be registered with '
            'actstream.' % document_class)
    if not is_installed(document_class):
        raise exception_class(
            'The document %r is not installed, please put the app "%s" in your '
            'INSTALLED_APPS setting.' % (document_class,
                                         document_class.__module__.split('.', 1)[0]))
    return document_class


class ActionableModelRegistry(dict):

    def register(self, *document_classes):
        for cls in document_classes:
            document_class = validate(cls)
            if document_class not in self:
                self[document_class] = setup_generic_relations(document_class)

    def unregister(self, *document_classes):
        for cls in document_classes:
            document_class = validate(cls)
            if document_class in self:
                del self[document_class]

    def check(self, document_class_or_object):
        if not isclass(document_class_or_object):
            document_class_or_object = document_class_or_object.__class__
        document_class = validate(document_class_or_object, RuntimeError)
        if document_class not in self:
            raise ImproperlyConfigured(
                'The model %s is not registered. Please use actstream.registry '
                'to register it.' % document_class.__name__)

registry = ActionableModelRegistry()
register = registry.register
unregister = registry.unregister
check = registry.check
