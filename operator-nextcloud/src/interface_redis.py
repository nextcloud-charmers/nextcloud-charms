#!/usr/bin/env python3
"""RedisRequires."""
import logging

from ops.framework import (
    EventBase,
    EventSource,
    Object,
    ObjectEvents,
)


logger = logging.getLogger()


class RedisAvailableEvent(EventBase):
    """RedisAvailableEvent."""


class RedisEvents(ObjectEvents):
    """Redis events."""

    redis_available = EventSource(RedisAvailableEvent)


class RedisClient(Object):
    """Redis Client Interface."""

    on = RedisEvents()

    def __init__(self, charm, relation_name):
        """Observe relation_changed."""
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        # Observe the relation-changed hook event and bind
        # self.on_relation_changed() to handle the event.
        self.framework.observe(
            self._charm.on[self._relation_name].relation_changed,
            self._on_relation_changed
        )

    def _on_relation_changed(self, event):
        event_unit_data = event.relation.data.get(event.unit)
        if not event_unit_data:
            event.defer()
            return
        password = event_unit_data.get('password')
        host = event_unit_data.get('hostname')
        port = event_unit_data.get('port')

        if (host and port):
            self._charm.set_redis_info({
                'redis_password': password,
                'redis_hostname': host,
                'redis_port': port,
            })
            self.on.redis_available.emit()
        else:
            logger.info("REDIS INFO NOT AVAILABLE")
            event.defer()
            return
