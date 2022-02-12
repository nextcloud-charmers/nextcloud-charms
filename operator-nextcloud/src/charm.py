#!/usr/bin/env python3
# Copyright 2020 Erik Lönroth
# See LICENSE file for licensing details.

import logging
import subprocess as sp
import sys
import os
import socket
from pathlib import Path
import json
import re

from ops.charm import CharmBase
from ops.main import main
from ops.framework import StoredState
from ops.lib import use

from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    ModelError,
)

import utils
from occ import Occ

from interface_http import HttpProvider
import interface_redis
import interface_mount

logger = logging.getLogger(__name__)

# POSTGRESQL interface documentation
# https://github.com/canonical/ops-lib-pgsql
pgsql = use("pgsql", 1, "postgresql-charmers@lists.launchpad.net")

NEXTCLOUD_ROOT = os.path.abspath('/var/www/nextcloud')
NEXTCLOUD_CONFIG_PHP = os.path.abspath('/var/www/nextcloud/config/config.php')
NEXTCLOUD_CEPH_CONFIG_PHP = os.path.join(NEXTCLOUD_ROOT, 'config/ceph.config.php')

EMOJI_ACTION_EVENT = "\U000026CF"
EMOJI_CORE_HOOK_EVENT = "\U0001F4CC"
EMOJI_RELATION_EVENT = "\U0001F9E9"
EMOJI_CLOUD = "\U00002601"
EMOJI_POSTGRES_EVENT = "\U0001F4BF"
EMOJI_COMPUTER_DISK = "\U0001F4BD"


class NextcloudCharm(CharmBase):
    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.db = pgsql.PostgreSQLClient(self, 'db')  # 'db' relation in metadata.yaml
        # The website relation is currentlt a haproxy serving as a reverse proxy.
        self.haproxy = HttpProvider(self, 'website', socket.getfqdn(), 80)
        self._stored.set_default(nextcloud_datadir='/var/www/nextcloud/data/',
                                 nextcloud_fetched=False,
                                 nextcloud_initialized=False,
                                 database_available=False,
                                 apache_configured=False,
                                 php_configured=False,
                                 ceph_configured=False,)
        self._stored.set_default(db_conn_str=None, db_uri=None, db_ro_uris=[])

        event_bindings = {
            self.on.install: self._on_install,
            self.on.config_changed: self._on_config_changed,
            self.on.start: self._on_start,
            self.on.leader_elected: self._on_leader_elected,
            self.db.on.database_relation_joined: self._on_database_relation_joined,
            self.db.on.master_changed: self._on_master_changed,
            self.on.update_status: self._on_update_status,
            self.on.cluster_relation_changed: self._on_cluster_relation_changed,
            self.on.cluster_relation_joined: self._on_cluster_relation_joined,
            self.on.cluster_relation_departed: self._on_cluster_relation_departed,
            self.on.cluster_relation_broken: self._on_cluster_relation_broken,
            self.on.set_trusted_domain_action: self._on_set_trusted_domain_action,
            self.on.ceph_relation_changed: self._on_ceph_relation_changed,
            self.on.datadir_storage_attached: self._on_datadir_storage_attached,
            self.on.datadir_storage_detaching: self._on_datadir_storage_detaching
        }

        # Relation: redis (Interface: redis)
        self._stored.set_default(redis_info=dict())
        self._redis = interface_redis.RedisClient(self, "redis")
        self.framework.observe(self._redis.on.redis_available,
                               self._on_redis_available)

        # Relation: shared-fs (Interface: mount)
        self._sharedfs = interface_mount.NFSMountClient(self, "shared-fs")
        self.framework.observe(self._sharedfs.on.nfsmount_available,
                               self._on_nfsmount_available)

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
        logger.debug(EMOJI_CORE_HOOK_EVENT + sys._getframe().f_code.co_name)
        self.unit.status = MaintenanceStatus("installing dependencies...")
        utils.install_apt_update()
        utils.install_dependencies()
        utils.install_backup_dependencies()
        if not self._stored.nextcloud_fetched:
            # Fetch nextcloud to /var/www/
            try:
                self.unit.status = MaintenanceStatus("installing (from resource).")
                tarfile_path = self.model.resources.fetch('nextcloud-tarfile')
                utils.extract_nextcloud(tarfile_path)
            except ModelError:
                self.unit.status = MaintenanceStatus("installing (from network).")
                utils.fetch_and_extract_nextcloud(self.config.get('nextcloud-tarfile'))
            utils.set_nextcloud_permissions(self)
            self.unit.status = MaintenanceStatus("installed")
            self._stored.nextcloud_fetched = True

    def _on_config_changed(self, event):
        """
        Any configuration change trigger a complete reconfigure of
        the php and apache and also a restart of apache.
        :param event:
        :return:
        """
        logger.debug(EMOJI_CORE_HOOK_EVENT + sys._getframe().f_code.co_name)
        self._config_apache()
        self._config_php()
        # TODO: let only the leader do changes to config. overwiteprotocol should
        # go that way rather than locally get changed since it its inconsistent with
        # how the rest of the config is done..
        self._config_overwriteprotocol()
        sp.check_call(['systemctl', 'restart', 'apache2.service'])
        if self.config.get('backup-host') and self._stored.nextcloud_initialized and self._stored.database_available:
            self.unit.status = MaintenanceStatus("Configuring backup")
            utils.config_backup(self.config, self._stored.nextcloud_datadir, self._stored.dbhost,
                                self._stored.dbuser, self._stored.dbpass)
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

    # Only leader is running this hook (verify this)
    def _on_leader_elected(self, event):
        logger.debug(EMOJI_CORE_HOOK_EVENT + sys._getframe().f_code.co_name)
        logger.debug("!!!!!!!! I'm new nextcloud leader !!!!!!!!")
        self.update_config_php_trusted_domains()

    def update_config_php_trusted_domains(self):
        """
        Updates trusted domains on peer relation
        Updates nextcloud via occ-command with trusted domains
        Updates the nexcloud_config peer relation data.
        This should only be run on the unit leader.
        """
        if not os.path.exists(NEXTCLOUD_CONFIG_PHP):
            return

        cluster_rel = self.model.relations['cluster'][0]
        rel_unit_ip = [cluster_rel.data[u]['ingress-address'] for u in cluster_rel.units]
        this_unit_ip = cluster_rel.data[self.model.unit]['ingress-address']
        rel_unit_ip.append(this_unit_ip)
        Occ.update_trusted_domains_peer_ips(rel_unit_ip)
        with open(NEXTCLOUD_CONFIG_PHP) as f:
            nextcloud_config = f.read()
            cluster_rel.data[self.app]['nextcloud_config'] = str(nextcloud_config)

    def update_relation_ceph_config_php(self):
        if not os.path.exists(NEXTCLOUD_CEPH_CONFIG_PHP):
            return
        cluster_rel = self.model.relations['cluster'][0]
        with open(NEXTCLOUD_CEPH_CONFIG_PHP) as f:
            ceph_config = f.read()
            cluster_rel.data[self.app]['ceph_config'] = str(ceph_config)

    def _on_cluster_relation_joined(self, event):
        logger.debug(EMOJI_CLOUD + sys._getframe().f_code.co_name)
        if self.model.unit.is_leader():
            if not self._stored.nextcloud_initialized:
                event.defer()
                return
            self.framework.breakpoint('joined')
            self.update_config_php_trusted_domains()

    def _on_cluster_relation_changed(self, event):
        """
        When a change on the config happens:
        Pull in configs from the peer (cluster) relation and write it to local disk.
        """
        logger.debug(EMOJI_CLOUD + sys._getframe().f_code.co_name)
        if not self.model.unit.is_leader():
            if 'nextcloud_config' not in event.relation.data[self.app]:
                event.defer()
                return

            nextcloud_config = event.relation.data[self.app]['nextcloud_config']
            with open(NEXTCLOUD_CONFIG_PHP, "w") as f:
                f.write(nextcloud_config)

            # TODO: only create .ocdata file for debug since it scale out
            # will only work with a shared-fs like NFS.
            self._make_ocdata_for_occ()

            if 'ceph_config' in event.relation.data[self.app]:
                ceph_config = event.relation.data[self.app]['ceph_config']
                with open(NEXTCLOUD_CEPH_CONFIG_PHP, "w") as f:
                    f.write(ceph_config)

            # Since config comes via root, we need to fix the perms here.
            utils.set_nextcloud_permissions(self)

    def _on_cluster_relation_departed(self, event):
        logger.debug(EMOJI_CLOUD + sys._getframe().f_code.co_name)
        self.framework.breakpoint('departed')
        if self.model.unit.is_leader():
            self.update_config_php_trusted_domains()

    def _on_cluster_relation_broken(self, event):
        logger.debug(EMOJI_CLOUD + sys._getframe().f_code.co_name)
        pass

    def _on_master_changed(self, event: pgsql.MasterChangedEvent):
        logger.debug(EMOJI_POSTGRES_EVENT + sys._getframe().f_code.co_name)
        self.unit.status = MaintenanceStatus("database master changed")
        if event.database != 'nextcloud':
            # Leader has not yet set requirements. Wait until next event,
            # or risk connecting to an incorrect database.
            return

        # Only leader gets to install or configure nextcloud.
        # Other peers will copy the configuration and therefore must trust that
        # nextcloud is initialized and that we have a database from config.
        if not self.model.unit.is_leader():
            self._stored.nextcloud_initialized = True
            self._stored.database_available = True

            # Perform a status update to indicate the status.
            self._on_update_status(event)
            return
        # The connection to the primary database has been created,
        # changed or removed. More specific events are available, but
        # most charms will find it easier to just handle the Changed
        # events. event.master is None if the master database is not
        # available, or a pgsql.ConnectionString instance.

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
                utils.set_nextcloud_permissions(self)
                self._init_nextcloud()
                self._add_initial_trusted_domain()
                utils.installCrontab()
                Occ.setBackgroundCron()
                if self._is_nextcloud_installed():
                    self._stored.nextcloud_initialized = True

    def _on_start(self, event):
        logger.debug(EMOJI_CORE_HOOK_EVENT + sys._getframe().f_code.co_name)
        if not self._is_nextcloud_installed():
            logger.debug("Nextcloud not installed, defering start.")
            event.defer()
            return
        try:
            sp.check_call(['systemctl', 'restart', 'apache2.service'])
            self._on_update_status(event)
            utils.open_port('80')
        except sp.CalledProcessError as e:
            print(e)
            sys.exit(-1)

    def _on_datadir_storage_attached(self, event):
        """
        If this event is fired, we are told to use a custom datadir.
        So, we set that here for this charm and remember that.
        """
        logger.debug(EMOJI_COMPUTER_DISK + sys._getframe().f_code.co_name)
        self._stored.nextcloud_datadir = str(event.storage.location)

    def _on_datadir_storage_detaching(self, event):
        logger.debug(EMOJI_COMPUTER_DISK + sys._getframe().f_code.co_name)
        pass

    def _on_add_missing_indices_action(self, event):
        logger.debug(EMOJI_ACTION_EVENT + sys._getframe().f_code.co_name)
        o = Occ.db_add_missing_indices()
        event.set_results({"occ-output": o})

    def _on_convert_filecache_bigint_action(self, event):
        """
        Action to convert-filecache-bigint on the database via occ
        This action places the site in maintenance mode to protect it
        while this action runs.
        """
        # TODO: Only leader should place site in maintenance.
        logger.debug(EMOJI_ACTION_EVENT + sys._getframe().f_code.co_name)
        Occ.maintenance_mode(enable=True)
        o = Occ.db_convert_filecache_bigint()
        event.set_results({"occ-output": o})
        # TODO: Only leader should place site off maintenance.
        Occ.maintenance_mode(enable=False)

    def _on_maintenance_action(self, event):
        """
        Action to take the site in or out of maintenance mode.
        :param event: boolean
        :return:
        """
        logger.debug(EMOJI_ACTION_EVENT + sys._getframe().f_code.co_name)
        o = Occ.maintenance_mode(enable=event.params['enable'])
        event.set_results({"occ-output": o})

    def _config_php(self):
        """
        Renders the phpmodule for nextcloud (nextcloud.ini)
        This is instead of manipulating the system wide php.ini
        which might be overwitten or changed from elsewhere.
        """
        self.unit.status = MaintenanceStatus("config php...")
        phpmod_context = {
            'max_file_uploads': self.config.get('php_max_file_uploads'),
            'upload_max_filesize': self.config.get('php_upload_max_filesize'),
            'post_max_size': self.config.get('php_post_max_size'),
            'memory_limit': self.config.get('php_memory_limit')
        }
        utils.config_php(phpmod_context, Path(self.charm_dir / 'templates'), 'nextcloud.ini.j2')
        self._stored.php_configured = True

    def _config_apache(self):
        """
        Configured apache
        """
        self.unit.status = MaintenanceStatus("config apache....")
        utils.config_apache2(Path(self.charm_dir / 'templates'), 'nextcloud.conf.j2')
        self._stored.apache_configured = True

    def _init_nextcloud(self):
        """
        Initializes nextcloud via the nextcloud occ interface.
        :return:
        """
        self.unit.status = MaintenanceStatus("initializing nextcloud...")
        ctx = {'dbtype': self._stored.dbtype,
               'dbname': self._stored.dbname,
               'dbhost': self._stored.dbhost,
               'dbpass': self._stored.dbpass,
               'dbuser': self._stored.dbuser,
               'adminpassword': self.config.get('admin-password'),
               'adminusername': self.config.get('admin-username'),
               'datadir': str(self._stored.nextcloud_datadir)
               }
        cp = Occ.maintenance_install(ctx)
        if cp.returncode == 0:
            self.unit.status = MaintenanceStatus("initialized nextcloud = OK.")
        else:
            self.unit.status = BlockedStatus("Initialization failed this is what I know: " + cp.stdout)
            logger.error("Error while initializing nextcloud.")
            sys.exit(-1)

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
        logger.debug(EMOJI_CORE_HOOK_EVENT + sys._getframe().f_code.co_name)

        if not self._stored.nextcloud_fetched:
            self.unit.status = BlockedStatus("Nextcloud not fetched.")

        elif not self._stored.nextcloud_initialized:
            self.unit.status = BlockedStatus("Nextcloud not initialized.")

        elif not self._stored.apache_configured:
            self.unit.status = BlockedStatus("Apache not configured.")

        elif not self._stored.php_configured:
            self.unit.status = BlockedStatus("PHP not configured.")

        elif not self._stored.database_available:
            self.unit.status = BlockedStatus("No database.")

        else:
            if self.model.unit.is_leader():
                # Only leader need to set app version
                v = self._nextcloud_version()
                self.unit.set_workload_version(v)
            # Set the active status to the running version.
            self.unit.status = ActiveStatus(v + " " + EMOJI_CLOUD)

    def set_redis_info(self, info: dict):
        self._stored.redis_info = info
        utils.config_redis(info, Path(self.charm_dir / 'templates'), 'redis.config.php.j2')

    def _on_redis_available(self, event):
        utils.config_redis(self._stored.redis_info,
                           Path(self.charm_dir / 'templates'), 'redis.config.php.j2')

        utils.config_redis_session(self._stored.redis_info,
                                   Path(self.charm_dir / 'templates'), 'redis_session.ini.j2')

        # When redis is configured, apache needs a restart.
        sp.run(['systemctl', 'restart', 'apache2.service'])

    def _on_set_trusted_domain_action(self, event):
        domain = event.params['domain']
        Occ.config_system_set_trusted_domains(domain, 1)
        self.update_config_php_trusted_domains()

    def _on_nfsmount_available(self, event):
        # systemd mount unit in place, so lets start it.
        cmd = "systemctl start media-nextcloud-data.mount"
        sp.run(cmd.split())

        # Put site in maintenance.
        # sudo -u www-data php /path/to/nextcloud/occ maintenance:mode --on
        Occ.maintenance_mode(enable=True)

        # Set ownership
        cmd = "chown www-data:www-data /media/nextcloud/data"
        sp.run(cmd.split())

        # Make sure the directory is a nextcloud datadir
        # touch $datadirectory/.ocdata (/media/nextcloud/data)
        cmd = "sudo -u www-data touch /media/nextcloud/data/.ocdata"
        sp.run(cmd.split())

        # Fix up permission on nfs mount
        cmd = "chmod 0770 /media/nextcloud/data/"
        sp.run(cmd.split())

        # Set new datadir
        cmd = "sudo -u www-data php occ config:system:set datadirectory --value=/media/nextcloud/data/"
        sp.run(cmd.split(), cwd="/var/www/nextcloud/")

        # Cleanup cache
        cmd = "sudo -u www-data php occ files:cleanup"
        sp.run(cmd.split(), cwd="/var/www/nextcloud/")

        # sudo -u www-data php /path/to/nextcloud/occ maintenance:mode --off
        Occ.maintenance_mode(enable=False)

    def _on_ceph_relation_changed(self, event):
        if not self.model.unit.is_leader():
            return
        ceph_user = event.relation.data[event.app].get('ceph_user')
        rados_gw_hostname = event.relation.data[event.app].get('rados_gw_hostname')
        rados_gw_port = event.relation.data[event.app].get('rados_gw_port')
        if ceph_user and rados_gw_hostname and rados_gw_port:
            self.framework.breakpoint('ceph-changed')
            ceph_user = json.loads(ceph_user)
            self.unit.status = MaintenanceStatus("Begin config ceph.")
            ceph_info = {
                'ceph_key': ceph_user['keys'][0]['access_key'],
                'ceph_secret': ceph_user['keys'][0]['secret_key'],
                'rados_gw_hostname': rados_gw_hostname,
                'rados_gw_port': rados_gw_port
            }
            utils.config_ceph(ceph_info, Path(self.charm_dir / 'templates'), 'ceph.config.php.j2')
            self._stored.ceph_configured = True
            self.unit.status = MaintenanceStatus("ceph config complete.")
            self.update_relation_ceph_config_php()

    def _config_overwriteprotocol(self):
        """
        Configures nextcloud overwriteprotocol to http or https.
        :return:
        """
        if self._stored.nextcloud_initialized:
            Occ.overwriteprotocol(self.config.get('overwriteprotocol'))

    def _make_ocdata_for_occ(self):
        """
        This create a .ocdata file which nextcloud wants or will error
        on all occ commands.
        """
        if not self._stored.nextcloud_datadir.exists():
            self._stored.nextcloud_datadir.mkdir()
        if not self._stored.nextcloud_datadir.joinpath('.ocdata').exists():
            self._stored.nextcloud_datadir.joinpath('.ocdata').touch()

    def _is_nextcloud_installed(self):
        status = Occ.status()
        match = re.findall(r'\{.*?\}', status.stdout)
        return json.loads(match[0])['installed']

    def _nextcloud_version(self):
        logger.debug("Determined nextcloud version: " + json.loads(Occ.status().stdout)['version'])
        return json.loads(Occ.status().stdout)['version']


if __name__ == "__main__":
    main(NextcloudCharm)
