import subprocess as sp
import logging
import json
import sys

logger = logging.getLogger(__name__)

class Occ:

    @staticmethod
    def config_system_set_trusted_domains(domain, index):
        """
        Adds a trusted domain to nextcloud config.php with occ
        """

        cmd = ("sudo -u www-data php /var/www/nextcloud/occ config:system:set"
               " trusted_domains {index}"
               " --value={domain} ").format(index=index, domain=domain)
        sp.call(cmd.split(), cwd='/var/www/nextcloud')

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
    def config_system_delete_trusted_domains():
        cmd = "sudo -u www-data php /var/www/nextcloud/occ \
                                  config:system:delete trusted_domains"
        sp.run(cmd.split(), cwd='/var/www/nextcloud')

    @staticmethod
    def config_system_get_trusted_domains():
        """
        Get all current trusted domains in config.php with occ
        return list
        """
        cmd = "sudo -u www-data php /var/www/nextcloud/occ \
                           config:system:get trusted_domains"
        output = sp.run(cmd.split(), cwd='/var/www/nextcloud',
                        stdout=sp.PIPE, universal_newlines=True)
        domains = output.stdout.split()
        return domains

    @staticmethod
    def update_trusted_domains_peer_ips(domains):
        current_domains = Occ.config_system_get_trusted_domains()
        # Copy 'localhost' and fqdn but replace all peers IP:s
        # with the ones currently available in the relation.
        new_domains = current_domains[0:2] + domains[:]
        Occ.config_system_delete_trusted_domains()
        for index, d in enumerate(new_domains):
            Occ.config_system_set_trusted_domains(d, index)

    @staticmethod
    def db_add_missing_indices():
        cmd = "sudo -u www-data php /var/www/nextcloud/occ db:add-missing-indices"
        output = sp.run(cmd.split(), cwd='/var/www/nextcloud',
                        stdout=sp.PIPE, universal_newlines=True)
        return output

    @staticmethod
    def db_convert_filecache_bigint():
        cmd = "sudo -u www-data php /var/www/nextcloud/occ \
               db:convert-filecache-bigint --no-interaction"
        output = sp.run(cmd.split(), cwd='/var/www/nextcloud',
                        stdout=sp.PIPE, universal_newlines=True)
        return output

    @staticmethod
    def maintenance_mode(enable):
        m = "--on" if enable else "--off"
        cmd = f"sudo -u www-data php /var/www/nextcloud/occ maintenance:mode {m}"
        output = sp.run(cmd.split(), cwd='/var/www/nextcloud',
                        stdout=sp.PIPE, universal_newlines=True)
        return output

    @staticmethod
    def maintenance_install(ctx):
        """
        Initializes nextcloud via the nextcloud occ interface.
        :return:
        """
        cmd = ("sudo -u www-data /usr/bin/php occ maintenance:install "
               "--database {dbtype} --database-name {dbname} "
               "--database-host {dbhost} --database-pass {dbpass} "
               "--database-user {dbuser} --admin-user {adminusername} "
               "--admin-pass {adminpassword} "
               "--data-dir {datadir} ").format(**ctx)
        sp.call(cmd.split(), cwd='/var/www/nextcloud')

    @staticmethod
    def status() -> dict:
        """
        Return dict with nextcloud status.
        """
        cmd = "sudo -u www-data /usr/bin/php occ status --output=json --no-warnings"
        try:
            output = sp.run(cmd.split(),
                            stdout=sp.PIPE,
                            cwd='/var/www/nextcloud',
                            universal_newlines=True).stdout
            returndict = json.loads(output.split()[-1])
        except sp.CalledProcessError as e:
            print(e)
            sys.exit(-1)
        return returndict

    @staticmethod
    def overwriteprotocol(protocol='http'):
        """
        Sets the overwrite protocol with occ
        :return:
        """
        if protocol == "http" or protocol == "https":
            logger.log(logging.INFO, "Setting overwriteprotocol to: " + protocol)
            cmd = ("sudo -u www-data /usr/bin/php occ config:system:set overwriteprotocol --value=" + protocol)
            sp.call(cmd.split(), cwd='/var/www/nextcloud')
        else:
            logger.log(logging.ERROR, "Unsupported overwriteprotocol provided as config: " + protocol)
            sys.exit(-1)