#!/usr/bin/env python3
# Copyright 2022 Joakim Nyman
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

import logging

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, WaitingStatus
import utils

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)


class CollaboraOfficeCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.update_status, self._on_update_status)

    def _on_install(self, _):
        utils.install_dependencies()
        self.update_status()

    def _on_config_changed(self, _):
        utils.configure(self.config)
        self.update_status()

    def _on_update_status(self, _):
        self.update_status()

    def update_status(self):
        if utils.is_service_running():
            self.unit.status = ActiveStatus("Service running")
        else:
            self.unit.status = WaitingStatus("Service not yet started")


if __name__ == "__main__":  # pragma: nocover
    main(CollaboraOfficeCharm)
