"""
Django>=1.5 compatibility utilities
"""

from django.conf import settings

user_model_label = getattr(settings, 'AUTH_USER_MODEL', 'auth.User')
username_field = lambda: getattr(get_user_model(), 'USERNAME_FIELD', 'username')

try:
    from mongoengine.django.mongo_auth.models import get_user_document as get_user_model
except ImportError:
    from mongoengine.django.auth import User
    get_user_model = lambda: User

try:
    from django.utils.encoding import smart_text
except ImportError:
    from django.utils.encoding import smart_unicode as smart_text


from mongoengine.base import get_document
class AppConfig(object):
    name = None

    def get_model(self, model_name):
        return get_document('{}.{}'.format(self.name.split('.')[-1], model_name))
