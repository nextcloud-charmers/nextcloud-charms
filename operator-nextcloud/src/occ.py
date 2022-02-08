import subprocess as sp
from subprocess import CompletedProcess
import logging
import sys

logger = logging.getLogger(__name__)


class Occ:

    @staticmethod
    def config_system_set_trusted_domains(domain, index) -> CompletedProcess:
        """
        Adds a trusted domain to nextcloud config.php with occ
        """

        cmd = ("sudo -u www-data php /var/www/nextcloud/occ config:system:set"
               " trusted_domains {index}"
               " --value={domain} ").format(index=index, domain=domain)
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def remove_trusted_domain(domain):
        """
        Removes a trusted domain from nextcloud with occ
        """
        current_domains = Occ.config_system_get_trusted_domains()
        if domain in current_domains:
            current_domains.remove(domain)
            # First delete all trusted domains from config.php
            # since they might have indices not in order.
            Occ.config_system_delete_trusted_domains()
            if current_domains:
                # Now, add all the domains with indices in order starting from 0
                for index, domain in enumerate(current_domains):
                    Occ.config_system_set_trusted_domains(domain, index)

    @staticmethod
    def config_system_delete_trusted_domains() -> CompletedProcess:
        cmd = "sudo -u www-data php /var/www/nextcloud/occ \
                                  config:system:delete trusted_domains"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def config_system_get_trusted_domains() -> CompletedProcess:
        """
        Get all current trusted domains in config.php with occ
        return list
        """
        cmd = "sudo -u www-data php /var/www/nextcloud/occ \
                           config:system:get trusted_domains"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)
        # domains = output.stdout.split()

    @staticmethod
    def update_trusted_domains_peer_ips(domains):
        current_domains = Occ.config_system_get_trusted_domains().stdout.split()
        # Copy 'localhost' and fqdn but replace all peers IP:s
        # with the ones currently available in the relation.
        new_domains = current_domains[0:2] + domains[:]
        Occ.config_system_delete_trusted_domains()
        for index, d in enumerate(new_domains):
            Occ.config_system_set_trusted_domains(d, index)

    @staticmethod
    def db_add_missing_indices() -> CompletedProcess:
        cmd = "sudo -u www-data php /var/www/nextcloud/occ db:add-missing-indices"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def db_convert_filecache_bigint() -> CompletedProcess:
        cmd = "sudo -u www-data php /var/www/nextcloud/occ \
               db:convert-filecache-bigint --no-interaction"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def maintenance_mode(enable) -> CompletedProcess:
        m = "--on" if enable else "--off"
        cmd = f"sudo -u www-data php /var/www/nextcloud/occ maintenance:mode {m}"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def maintenance_install(ctx) -> CompletedProcess:
        """
        Initializes nextcloud via the nextcloud occ interface.
        :return: <CompletedProcess>
        """
        cmd = ("sudo -u www-data /usr/bin/php occ maintenance:install "
               "--database {dbtype} --database-name {dbname} "
               "--database-host {dbhost} --database-pass {dbpass} "
               "--database-user {dbuser} --admin-user {adminusername} "
               "--admin-pass {adminpassword} "
               "--data-dir {datadir} ").format(**ctx)
        cp = sp.run(cmd.split(), cwd='/var/www/nextcloud',
                    stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)
        if not cp.returncode == 0:
            logger.error("Failed initializing nextcloud: " + str(cp))
        else:
            # TODO: Dont log the cp object since it may have passwords in it. Strip it away here?
            logger.info("Suceess initializing nextcloud: " + str(cp))

        cp.args=['REMOVED'] # Remove potential password from reaching the log.
        return cp

    @staticmethod
    def status() -> CompletedProcess:
        """
        Returns CompletedProcess with nextcloud status in .stdout as json.
        """
        cmd = "sudo -u www-data /usr/bin/php occ status --output=json --no-warnings"
        return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                      stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)

    @staticmethod
    def overwriteprotocol(protocol='http') -> CompletedProcess:
        """
        Sets the overwrite protocol with occ
        :return:
        """
        if protocol == "http" or protocol == "https":
            logger.info("Setting overwriteprotocol to: " + protocol)
            cmd = ("sudo -u www-data /usr/bin/php occ config:system:set overwriteprotocol --value=" + protocol)
            return sp.run(cmd.split(), cwd='/var/www/nextcloud',
                          stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)
        else:
            logger.error("Unsupported overwriteprotocol provided as config: " + protocol)
            sys.exit(-1)
