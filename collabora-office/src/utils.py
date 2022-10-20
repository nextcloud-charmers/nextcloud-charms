#!/usr/bin/env python3

import subprocess as sp
import lsb_release
from pathlib import Path
import jinja2
import os


def install_dependencies():
    """
    Installs package dependencies for the supported distros.
    + focal
    + jammy
    :return:
    """
    if 'focal' == lsb_release.get_distro_information()['CODENAME']:
        _install_dependencies('focal')
    elif 'jammy' == lsb_release.get_distro_information()['CODENAME']:
        _install_dependencies('jammy')
    else:
        raise RuntimeError("No valid series found to install package dependencies for")


def _install_dependencies(distro):
    sp.run(['wget', 'https://collaboraoffice.com/downloads/gpg/collaboraonline-release-keyring.gpg'], cwd='/usr/share/keyrings')

    if distro == 'focal':
        ubuntu_version = '2004'
    elif distro == 'jammy':
        ubuntu_version = '2204'
    else:
        raise Exception(f'{distro} is not a supported distro.')

    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader('templates')
    ).get_template('collaboraoffice.sources.j2')
    target = Path('/etc/apt/sources.list.d/collaboraonline.sources')
    target.write_text(template.render({'version': ubuntu_version}))

    sp.run(['apt', 'update'])

    packages = ['coolwsd',
                'code-brand']
    command = ["apt", "install", "-y"]
    command.extend(packages)
    sp.run(command, check=True)


def configure(config):
    sp.run(['coolconfig', 'set', 'ssl.enable', str(config.get("ssl-enable"))])
    sp.run(['coolconfig', 'set', 'ssl.termination', str(config.get("ssl-termination"))])
    sp.run(['coolconfig', 'set', 'storage.wopi.host', config.get("storage-wopi-host")])
    sp.run(['systemctl', 'restart', 'coolwsd'])


def is_service_running():
    service_started = os.system('systemctl status coolwsd')
    if service_started != 0:
        return False
    else:
        return True
