#!/usr/bin/python3
"""HTTP interface (provides side)."""

from ops.framework import Object
from ops.charm import RelationBrokenEvent, RelationDepartedEvent
import logging
from jinja2 import Environment
import yaml


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
        self._haproxy_service_name = "nextcloud"
        # The services key to pass to haproxy

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
        We would normally be able to send information here, but we don't want to
        give the haproxy this information until we are really
        """
        haproxy_ip = event.relation.data[event.unit]['private-address']
        logging.debug("Joining with haproxy: " + haproxy_ip )

        # TODO: We can add this to trustred proxies here


    def _on_relation_changed(self, event):
        if not self.charm._is_nextcloud_installed():
            logging.debug("Not Installed, not sending data yet, defering event until nextcloud is ready.")
            event.defer()
            return
        else:
            haproxy_ip = event.relation.data[event.unit]['private-address']
            logging.debug("Nextcloud installed, sending relation data to remote haproxy at." + str(haproxy_ip))
            event.relation.data[self.model.unit]['hostname'] = self._hostname
            event.relation.data[self.model.unit]['port'] = str(self._port)
            event.relation.data[self.model.unit]['service_name'] = "nextcloud"

    def _on_relation_departed(self, event: RelationDepartedEvent):
        pass

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        pass

    # TODO: Possibly dead code here since we dont send anything to haproxy this way now.
    def _renderServicesYaml(self):
        YAML = self._haproxyServicesYaml
        ip = str(self.model.get_binding("website").network.bind_address)
        r = Environment().from_string(YAML).render(address=ip,
                                                   port=self._port,
                                                   unitid=self.model.unit.name.rsplit('/', 1)[1])
        try:
            return str(yaml.safe_load(r))
        except yaml.YAMLError as exc:
            print(exc)
