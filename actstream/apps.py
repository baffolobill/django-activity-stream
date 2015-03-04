from actstream.signals import action
from actstream.actions import action_handler
from actstream.compat import AppConfig


class ActstreamConfig(AppConfig):
    name = 'actstream'

    def ready(self):
        action.connect(action_handler, dispatch_uid='actstream.models')

