#!/usr/bin/python3
"""HTTP interface (provides side)."""

from ops.framework import Object
from ops.charm import RelationBrokenEvent, RelationDepartedEvent
import logging


class HttpProvider(Object):
    """
    Http interface provider interface.
    """

    def __init__(self, charm, relation_name, hostname="", port=80):
        """Set the initial data.
        """
        super().__init__(charm, relation_name)
        self.charm = charm
        self._relation_name = relation_name
        self._hostname = hostname  # FQDN of host passed on in relations
        self._port = port
        self.framework.observe(
            charm.on[relation_name].relation_joined, self._on_relation_joined
        )
        self.framework.observe(
            charm.on[relation_name].relation_changed, self._on_relation_changed
        )
        self.framework.observe(
            charm.on[relation_name].relation_departed, self._on_relation_departed
        )
        self.framework.observe(
            charm.on[relation_name].relation_broken, self._on_relation_broken
        )

    def _on_relation_joined(self, event):
        """
        We use this event for passing on hostname and port.
        :param event:
        :return:
        """
        logging.debug("Joining with haproxy.")

    def _on_relation_changed(self, event):
        if not self.charm._is_nextcloud_installed():
            logging.debug("Not Installed, not sending data yet, defering event until nextcloud is ready.")
            event.defer()
            return
        else:
            logging.debug("Nextcloud installed, sending relation data to remote haproxy.")
            event.relation.data[self.model.unit]['hostname'] = self._hostname
            event.relation.data[self.model.unit]['port'] = str(self._port)

    def _on_relation_departed(self, event: RelationDepartedEvent):
        pass

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        pass
