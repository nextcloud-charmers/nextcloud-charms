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
        # The services key to pass to haproxy
        self._haproxyServicesYaml = """
- service_name: nextcloud
  service_host: 0.0.0.0
  service_port: 443
  crts: [DEFAULT]
  service_options:
      - balance leastconn
      - option forwardfor
      - http-request set-header X-Forwarded-Port %[dst_port]
      - http-request add-header X-Forwarded-Proto https if { ssl_fc }
      - http-check expect status 200
      - acl url_discovery path /.well-known/caldav /.well-known/carddav
      - http-request redirect location /remote.php/dav/ code 301 if url_discovery
  servers: [[nextcloud_unit_{{ unitid }}, {{ address }}, {{ port }}, 'cookie S{i} check']]
"""
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
            event.relation.data[self.model.unit]['services'] = self._renderServicesYaml()

    def _on_relation_departed(self, event: RelationDepartedEvent):
        pass

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        pass

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
