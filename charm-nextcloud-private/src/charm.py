#!/usr/bin/env python3
# Copyright 2020 Erik Lönroth
# See LICENSE file for licensing details.

import logging
import shutil
import subprocess as sp
import sys
import os
import socket
from pathlib import Path

from ops.charm import CharmBase
from ops.main import main
from ops.framework import StoredState
from ops.lib import use

from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, ModelError


from nextcloud import utils
from nextcloud.occ import Occ

from interface_http import HttpProvider
import interface_redis

logger = logging.getLogger(__name__)

# POSTGRESQL interface documentation
# https://github.com/canonical/ops-lib-pgsql
pgsql = use("pgsql", 1, "postgresql-charmers@lists.launchpad.net")

NEXTCLOUD_ROOT = os.path.abspath('/var/www/nextcloud')
NEXTCLOUD_CONFIG_PHP = os.path.abspath('/var/www/nextcloud/config/config.php')


class NextcloudPrivateCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.db = pgsql.PostgreSQLClient(self, 'db')  # 'db' relation in metadata.yaml
        # The website provider takes care of incoming relations on the http interface.
        self.website = HttpProvider(self, 'website', socket.getfqdn(), 80)
        self._stored.set_default(local_storage_attached=False,
                                 nextcloud_fetched=False,
                                 nextcloud_initialized=False,
                                 database_available=False,
                                 apache_configured=False,
                                 php_configured=False)
        self._stored.set_default(db_conn_str=None, db_uri=None, db_ro_uris=[])

        event_bindings = {
            self.on.install: self._on_install,
            self.on.config_changed: self._on_config_changed,
            self.on.start: self._on_start,
            self.db.on.database_relation_joined: self._on_database_relation_joined,
            self.db.on.master_changed: self._on_master_changed,
            self.on.update_status: self._on_update_status,
            self.on.data_storage_attached: self._on_data_storage_attached,
            self.on.set_trusted_domain_action: self._on_set_trusted_domain_action
        }

        # REDIS
        self._stored.set_default(redis_info=dict())
        self._redis = interface_redis.RedisClient(self, "redis")
        self.framework.observe(self._redis.on.redis_available, self._on_redis_available)

        for event, handler in event_bindings.items():
            self.framework.observe(event, handler)

        action_bindings = {
            self.on.add_missing_indices_action: self._on_add_missing_indices_action,
            self.on.convert_filecache_bigint_action: self._on_convert_filecache_bigint_action,
            self.on.maintenance_action: self._on_maintenance_action
        }

        for action, handler in action_bindings.items():
            self.framework.observe(action, handler)

    def _on_install(self, event):
        self.unit.status = MaintenanceStatus("Begin installing dependencies...")
        utils.install_dependencies()
        self.unit.status = MaintenanceStatus("Dependencies installed")
        if not self._stored.nextcloud_fetched:
            # Fetch nextcloud to /var/www/
            self.unit.status = MaintenanceStatus("Begin fetching sources.")
            try:
                tarfile_path = self.model.resources.fetch('nextcloud-tarfile')
                utils.extract_nextcloud(tarfile_path)
            except ModelError:
                utils.fetch_and_extract_nextcloud(self.config.get('nextcloud-tarfile'))
            self.unit.status = MaintenanceStatus("Sources installed")
            self._stored.nextcloud_fetched = True

        if self._stored.nextcloud_fetched and self._stored.local_storage_attached:
            sp.check_call(['systemctl', 'start', 'var-www-nextcloud-data.mount'])

    def _on_config_changed(self, event):
        """
        Any configuration change trigger a complete reconfigure of
        the php and apache and also a restart of apache.
        :param event:
        :return:
        """
        self.unit.status = MaintenanceStatus("Begin config apache2.")
        utils.config_apache2(Path(self.charm_dir / 'templates'), 'nextcloud.conf.j2')
        self._stored.apache_configured = True
        self.unit.status = MaintenanceStatus("apache2 config complete.")
        self._config_php()
        # self._config_website()
        sp.check_call(['systemctl', 'restart', 'apache2.service'])
        self._on_update_status(event)

    def _on_database_relation_joined(self, event: pgsql.DatabaseRelationJoinedEvent):
        if self.model.unit.is_leader():
            # Provide requirements to the PostgreSQL server.
            event.database = 'nextcloud'  # Request database named mydbname
            event.extensions = ['citext']  # Request the citext extension installed
        elif event.database != 'nextcloud':
            # Leader has not yet set requirements. Defer, incase this unit
            # becomes leader and needs to perform that operation.
            event.defer()
            return

    def _on_master_changed(self, event: pgsql.MasterChangedEvent):
        if event.database != 'nextcloud':
            # Leader has not yet set requirements. Wait until next event,
            # or risk connecting to an incorrect database.
            return
        # Only install nextcloud first time. Other peers will copy the configuration
        if not self.model.unit.is_leader():
            return
        # The connection to the primary database has been created,
        # changed or removed. More specific events are available, but
        # most charms will find it easier to just handle the Changed
        # events. event.master is None if the master database is not
        # available, or a pgsql.ConnectionString instance.

        logger.debug("=== Database master_changed event ===")

        self._stored.db_conn_str = None if event.master is None else event.master.conn_str
        self._stored.db_uri = None if event.master is None else event.master.uri
        self._stored.dbname = None if event.master is None else event.master.dbname
        self._stored.dbuser = None if event.master is None else event.master.user
        self._stored.dbpass = None if event.master is None else event.master.password
        self._stored.dbhost = None if event.master is None else event.master.host
        self._stored.dbport = None if event.master is None else event.master.port
        self._stored.dbtype = None if event.master is None else 'pgsql'

        if event.master and event.database == 'nextcloud':
            self._stored.database_available = True
            if not self._stored.nextcloud_initialized:
                utils.set_nextcloud_permissions()
                self._init_nextcloud()
                self._add_initial_trusted_domain()
                installed = Occ.status()['installed']
                if installed:
                    logger.debug("===== Nextcloud install_status: {}====".format(installed))
                    self._stored.nextcloud_initialized = True

    def _on_start(self, event):
        if not self._stored.nextcloud_initialized:
            event.defer()
            return
        try:
            sp.check_call(['systemctl', 'restart', 'apache2.service'])
            self._on_update_status(event)
            utils.open_port('80')
        except sp.CalledProcessError as e:
            print(e)
            sys.exit(-1)

    # ACTIONS

    def _on_add_missing_indices_action(self, event):
        o = Occ.db_add_missing_indices()
        event.set_results({"occ-output": o})

    def _on_convert_filecache_bigint_action(self, event):
        """
        Action to convert-filecache-bigint on the database via occ
        This action places the site in maintenance mode to protect it
        while this action runs.
        """
        Occ.maintenance_mode(enable=True)
        o = Occ.db_convert_filecache_bigint()
        event.set_results({"occ-output": o})
        Occ.maintenance_mode(enable=False)

    def _on_maintenance_action(self, event):
        """
        Action to take the site in or out of maintenance mode.
        :param event: boolean
        :return:
        """
        o = Occ.maintenance_mode(enable=event.params['enable'])
        event.set_results({"occ-output": o})

    def _config_php(self):
        """
        Renders the phpmodule for nextcloud (nextcloud.ini)
        This is instead of manipulating the system wide php.ini
        which might be overwitten or changed from elsewhere.
        """
        self.unit.status = MaintenanceStatus("Begin config php.")
        phpmod_context = {
            'max_file_uploads': self.config.get('php_max_file_uploads'),
            'upload_max_filesize': self.config.get('php_upload_max_filesize'),
            'post_max_size': self.config.get('php_post_max_size'),
            'memory_limit': self.config.get('php_memory_limit')
        }
        utils.config_php(phpmod_context, Path(self.charm_dir / 'templates'), 'nextcloud.ini.j2')
        self._stored.php_configured = True
        self.unit.status = MaintenanceStatus("php config complete.")

    def _init_nextcloud(self):
        """
        Initializes nextcloud via the nextcloud occ interface.
        :return:
        """
        self.unit.status = MaintenanceStatus("Begin initializing nextcloud...")
        ctx = {'dbtype': self._stored.dbtype,
               'dbname': self._stored.dbname,
               'dbhost': self._stored.dbhost,
               'dbpass': self._stored.dbpass,
               'dbuser': self._stored.dbuser,
               'adminpassword': self.config.get('admin-password'),
               'adminusername': self.config.get('admin-username'),
               'datadir': '/var/www/nextcloud/data'
               }
        Occ.maintenance_install(ctx)

    def _add_initial_trusted_domain(self):
        """
        Adds in 2 trusted domains:
        1. ingress address.
        2. fqdn config
        :return:
        """
        # Adds the fqdn to trusted domains (if set)
        if self.config['fqdn']:
            Occ.config_system_set_trusted_domains(self.config['fqdn'], 1)
        ingress_addr = self.model.get_binding('website').network.ingress_address
        # Adds the ingress_address to trusted domains
        Occ.config_system_set_trusted_domains(ingress_addr, 2)

    def _on_update_status(self, event):
        """
        Evaluate the internal state to report on status.
        """
        if not self._stored.nextcloud_fetched:
            self.unit.status = BlockedStatus("Nextcloud not fetched.")

        elif not self._stored.database_available:
            self.unit.status = BlockedStatus("No database available.")

        elif not self._stored.nextcloud_initialized:
            self.unit.status = BlockedStatus("Nextcloud not initialized.")

        elif not self._stored.apache_configured:
            self.unit.status = BlockedStatus("Apache not configured.")

        elif not self._stored.php_configured:
            self.unit.status = BlockedStatus("PHP not configured.")

        else:
            if self.model.unit.is_leader():
                self.unit.set_workload_version(Occ.status()['version'])
            self.unit.status = ActiveStatus("Ready")

    def set_redis_info(self, info: dict):
        self._stored.redis_info = info
        utils.config_redis(info, Path(self.charm_dir / 'templates'), 'redis.config.php.j2')

    def _on_redis_available(self, event):
        utils.config_redis(self._stored.redis_info,
                           Path(self.charm_dir / 'templates'), 'redis.config.php.j2')

    def install_mount_unitfile(self):
        """
        Install unitfile for mounting data dir.
        """
        shutil.copyfile('templates/etc/systemd/system/var-www-nextcloud-data.mount',
                        '/etc/systemd/system/var-www-nextcloud-data.mount')
        sp.check_call(['systemctl', 'daemon-reload'])

    def _on_data_storage_attached(self, event):
        """
        Local storage is managed by Juju, so we can just pass on the
        This happens normally after the install hook.
        Don't allow attaching storage after deploy.
        StorageAttachedEvent and Juju has taken care of the rest.
        """
        self._stored.local_storage_attached = True
        if self._stored.nextcloud_initialized:
            self.unit.status = BlockedStatus("Adding storage after installation is not supported.")
        else:
            self.unit.status = MaintenanceStatus("Adding local data storage.")
            self.install_mount_unitfile()

    def _on_set_trusted_domain_action(self, event):
        domain = event.params['domain']
        Occ.config_system_set_trusted_domains(domain, 1)

    def _on_data_storage_detaching(self, event):
        """
        Remove the local storage flag.
        """
        self.unit.status = MaintenanceStatus("Removed data storage.")
        self._stored.local_storage_attached = False


if __name__ == "__main__":
    main(NextcloudPrivateCharm)
