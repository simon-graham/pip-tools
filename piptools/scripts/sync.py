# coding: utf-8
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import sys
import shlex
import optparse

import pip

from .. import click, sync
from ..exceptions import PipToolsError
from ..logging import log
from ..utils import assert_compatible_pip_version, flat_map

# Make sure we're using a compatible version of pip
assert_compatible_pip_version()

DEFAULT_REQUIREMENTS_FILE = 'requirements.txt'


def requirements_parser(src_files):
    parser = pip.req.req_file.build_parser()
    all_txt = b''
    for r in src_files:
        with open(r, 'r') as req_txt:
            for ln in req_txt.readlines():
                if not ln.startswith(b'#'):     # ignore comments
                    _, options_str = pip.req.req_file.break_args_options(ln)
                    all_txt += options_str
    txt_file_flags = None
    if all_txt:
        txt_file_flags, _ = parser.parse_args(shlex.split(all_txt), None)
    return txt_file_flags


@click.command()
@click.version_option()
@click.option('-n', '--dry-run', is_flag=True, help="Only show what would happen, don't change anything")
@click.option('--force', is_flag=True, help="Proceed even if conflicts are found")
@click.option('-f', '--find-links', multiple=True, help="Look for archives in this directory or on this HTML page", envvar='PIP_FIND_LINKS')  # noqa
@click.option('-i', '--index-url', help="Change index URL (defaults to PyPI)", envvar='PIP_INDEX_URL')
@click.option('--extra-index-url', multiple=True, help="Add additional index URL to search", envvar='PIP_EXTRA_INDEX_URL')  # noqa
@click.option('--no-index', is_flag=True, help="Ignore package index (only looking at --find-links URLs instead)")
@click.option('-q', '--quiet', default=False, is_flag=True, help="Give less output")
@click.option('-p', '--prefix', required=False, help="prefix is installation dir where lib, bin and other top-level "
                                                     "folders live")
@click.option('--no-cache', required=False, is_flag=True, help="Disable the cache")
@click.argument('src_files', required=False, type=click.Path(exists=True), nargs=-1)
def cli(dry_run, force, find_links, index_url, extra_index_url, no_index, quiet, prefix, no_cache, src_files):
    """Synchronize virtual environment with requirements.txt."""
    if not src_files:
        if os.path.exists(DEFAULT_REQUIREMENTS_FILE):
            src_files = (DEFAULT_REQUIREMENTS_FILE,)
        else:
            msg = 'No requirement files given and no {} found in the current directory'
            log.error(msg.format(DEFAULT_REQUIREMENTS_FILE))
            sys.exit(2)

    if any(src_file.endswith('.in') for src_file in src_files):
        msg = ('Some input files have the .in extension, which is most likely an error and can '
               'cause weird behaviour.  You probably meant to use the corresponding *.txt file?')
        if force:
            log.warning('WARNING: ' + msg)
        else:
            log.error('ERROR: ' + msg)
            sys.exit(2)

    requirements = flat_map(lambda src: pip.req.parse_requirements(src, session=True),
                            src_files)

    try:
        requirements = sync.merge(requirements, ignore_conflicts=force)
    except PipToolsError as e:
        log.error(str(e))
        sys.exit(2)

    installed_dists = pip.get_installed_distributions(skip=[])
    to_install, to_uninstall = sync.diff(requirements, installed_dists)

    install_flags = []
    # Add flags from requirements.txt
    requirements_flags = requirements_parser(src_files)
    if requirements_flags:
        for link in requirements_flags.find_links:
            install_flags.extend(['-f', link])
        for host in requirements_flags.trusted_hosts:
            install_flags.extend(['--trusted-host', host])

    # Add flags from command line options
    for link in find_links or []:
        install_flags.extend(['-f', link])
    if no_index:
        install_flags.append('--no-index')
    if index_url:
        install_flags.extend(['-i', index_url])
    if extra_index_url:
        for extra_index in extra_index_url:
            install_flags.extend(['--extra-index-url', extra_index])
    if prefix:
        install_flags.extend(['--prefix', prefix])
    if no_cache:
        install_flags.extend(['--no-cache-dir'])
    sys.exit(sync.sync(to_install, to_uninstall, verbose=(not quiet), dry_run=dry_run,
                       install_flags=install_flags))
