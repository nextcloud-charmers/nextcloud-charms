import subprocess as sp
import sys

import lsb_release
import requests
import tarfile
from pathlib import Path
import jinja2
import io
# from charm import NextcloudCharm


def _modify_port(start=None, end=None, protocol='tcp', hook_tool="open-port"):
    assert protocol in {'tcp', 'udp', 'icmp'}
    if protocol == 'icmp':
        start = None
        end = None

    if start and end:
        port = f"{start}-{end}/"
    elif start:
        port = f"{start}/"
    else:
        port = ""
    sp.run([hook_tool, f"{port}{protocol}"])


def enable_ping():
    _modify_port(None, None, protocol='icmp', hook_tool="open-port")


def disable_ping():
    _modify_port(None, None, protocol='icmp', hook_tool="close-port")


def open_port(start, end=None, protocol="tcp"):
    _modify_port(start, end, protocol=protocol, hook_tool="open-port")


def close_port(start, end=None, protocol="tcp"):
    _modify_port(start, end, protocol=protocol, hook_tool="close-port")


def set_nextcloud_permissions(charm):
    """
    Set ownershow to www-data for nextcloud locations.
    """
    _datadir = str(charm._stored.nextcloud_datadir)
    cmd = ['chown', '-R', 'www-data:www-data', '/var/www/nextcloud', _datadir]
    sp.run(cmd, cwd='/var/www/nextcloud')


def install_dependencies():
    """
    Installs package dependencies for the supported distros.
    + focal
    + bionic
    :return:
    """
    if 'focal' == lsb_release.get_distro_information()['CODENAME']:
        _install_dependencies_focal()
    elif 'bionic' == lsb_release.get_distro_information()['CODENAME']:
        _install_dependencies_bionic()
    else:
        raise RuntimeError("No valid series found to install package dependencies for")


def install_apt_update():
    command = ["sudo", "apt", "update", "-y"]
    sp.run(command, check=True)


def _install_dependencies_bionic():
    """
    Install packages that is needed by nextcloud to work with this charm.
    Inspired by: https://github.com/nextcloud/vm/blob/master/nextcloud_install_production.sh
    """
    try:
        packages = ['apache2',
                    'libapache2-mod-php7.2',
                    'php7.2-gd',
                    'php7.2-json',
                    'php7.2-mysql',
                    'php7.2-pgsql',
                    'php7.2-curl',
                    'php7.2-mbstring',
                    'php7.2-intl',
                    'php7.2-imagick',
                    'php7.2-zip',
                    'php7.2-xml',
                    'php-apcu',
                    'php-redis',
                    'php-smbclient']
        command = ["sudo", "apt", "install", "-y"]
        command.extend(packages)
        sp.run(command, check=True)
    except sp.CalledProcessError as e:
        print(e)
        sys.exit(-1)


def _install_dependencies_focal():
    """
    Install packages that is needed by nextcloud to work with this charm.
    Inspired by: https://github.com/nextcloud/vm/blob/master/nextcloud_install_production.sh
    :return:
    """
    try:
        packages = ['apache2',
                    'libapache2-mod-php7.4',
                    'php7.4-fpm',
                    'php7.4-intl',
                    'php7.4-ldap',
                    'php7.4-imap',
                    'php7.4-gd',
                    'php7.4-pgsql',
                    'php7.4-curl',
                    'php7.4-xml',
                    'php7.4-zip',
                    'php7.4-mbstring',
                    'php7.4-soap',
                    'php7.4-json',
                    'php7.4-gmp',
                    'php7.4-bz2',
                    'php7.4-bcmath',
                    'php7.4-imagick',
                    'php-pear',
                    'php-apcu',
                    'php-redis']
        command = ["sudo", "apt", "install", "-y"]
        command.extend(packages)
        sp.run(command, check=True)
    except sp.CalledProcessError as e:
        print(e)
        sys.exit(-1)


def fetch_and_extract_nextcloud(tarfile_url):
    """
    Fetch and Install nextcloud from internet
    Sources are about 100M.
    """
    # tarfile_url = 'https://download.nextcloud.com/server/releases/nextcloud-18.0.3.tar.bz2'
    # checksum = '7b67e709006230f90f95727f9fa92e8c73a9e93458b22103293120f9cb50fd72'
    try:
        response = requests.get(tarfile_url, allow_redirects=True, stream=True)
        dst = Path('/var/www/')
        with tarfile.open(fileobj=io.BytesIO(response.content), mode='r:bz2') as tfile:
            tfile.extractall(path=dst)
    except sp.CalledProcessError as e:
        print(e)
        sys.exit(-1)


def extract_nextcloud(tarfile_path):
    """
    Install nextcloud from tarfile
    """
    dst = Path('/var/www/')
    with tarfile.open(tarfile_path, mode='r:bz2') as tfile:
        tfile.extractall(path=dst)


def config_apache2(templates_path, template):
    """
    Configures apache2
    """
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_path)
    ).get_template(template)
    target = Path('/etc/apache2/sites-available/nextcloud.conf')
    ctx = {}
    target.write_text(template.render(ctx))
    # Enable required modules.
    for module in ['rewrite', 'headers', 'env', 'dir', 'mime', 'setenvif', 'proxy_fcgi']:
        sp.call(['a2enmod', module])
    # Disable default site
    sp.check_call(['a2dissite', '000-default'])
    # Enable nextcloud site (wich will be default)
    sp.check_call(['a2ensite', 'nextcloud'])


def install_nfs_systemd_mount(templates_path, template, ctx):
    """
    Installs nfs systemd.mount unit file
    ctx = {'nfs_host': <iphostname>, 'appname': <appname>}
    """
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_path)
    ).get_template(template)
    target = Path('/etc/systemd/system/media-nextcloud-data.mount')
    target.write_text(template.render(ctx))
    sp.call(['systemctl', 'daemon-reload'])


def config_php(phpmod_context, templates_path, template):
    """
    Renders the phpmodule for nextcloud (nextcloud.ini)
    This is instead of manipulating the system wide php.ini
    which might be overwitten or changed from elsewhere.
    """
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_path)
    ).get_template(template)
    target_72 = Path('/etc/php/7.2/mods-available/nextcloud.ini')
    target_74 = Path('/etc/php/7.4/mods-available/nextcloud.ini')
    if get_phpversion() == "7.4":
        target_74.write_text(template.render(phpmod_context))
    elif get_phpversion() == "7.2":
        target_72.write_text(template.render(phpmod_context))
    sp.check_call(['phpenmod', 'nextcloud'])


def config_redis(redis_info, templates_path, template):
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_path)
    ).get_template(template)
    target = Path('/var/www/nextcloud/config/redis.config.php')
    target.write_text(template.render(redis_info))


def config_redis_session(redis_info, templates_path, template):
    """ Puts redis session manager in place and enables the mod"""
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_path)
    ).get_template(template)
    target_72 = Path('/etc/php/7.2/mods-available/redis_session.ini')
    target_74 = Path('/etc/php/7.4/mods-available/redis_session.ini')
    if get_phpversion() == "7.4":
        target_74.write_text(template.render(redis_info))
    elif get_phpversion() == "7.2":
        target_72.write_text(template.render(redis_info))
    sp.check_call(['phpenmod', 'redis_session'])


def config_ceph(ceph_info, templates_path, template):
    """
    Renders the phpmodule for nextcloud (nextcloud.ini)
    This is instead of manipulating the system wide php.ini
    which might be overwitten or changed from elsewhere.
    """
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(templates_path)
    ).get_template(template)
    target = Path('/var/www/nextcloud/config/ceph.config.php')
    target.write_text(template.render(ceph_info))


def get_phpversion():
    """
    Get php version X.Y from the running system.
    Supports
    - 7.2 (bionic),
    - 7.4 (focal)
    :return: string
    """
    response = sp.check_output(['php', '-v']).decode()
    lines = response.split("\n")
    if "PHP 7.4" in lines[0]:
        return "7.4"
    elif "PHP 7.2" in lines[0]:
        return "7.2"
    else:
        raise RuntimeError("No valid PHP version found in check")
