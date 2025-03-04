#! /usr/bin/env python3
# vim: set fileencoding=utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 smartindent ft=python
# pylint: disable=fixme,missing-module-docstring,missing-class-docstring,wrong-import-position

import os
import sys
import logging
import argparse
import urllib3
import hiyapyco
from pprint import pprint
import base64

# in case we have the jira and zammad as git submodule
_BASEDIR_ = os.path.dirname(os.path.abspath(__file__))
for submodule in ['jira', 'zammad_py']:
    sys.path.append(os.path.join(_BASEDIR_, submodule))

# https://jira.readthedocs.io/api.html#jira.client.JIRA
from jira import JIRA
from jira import JIRAError
# https://zammad-py.readthedocs.io/en/latest/usage.html
from zammad_py import ZammadAPI

import j2z.user
import j2z.issue
import j2z.comment

urllib3.disable_warnings()

class LoggingAction(argparse.Action):
    # pylint: disable=redefined-outer-name
    def __call__(self, parser, namespace, values, option_string=None):
        logger = logging.getLogger()
        logger.setLevel(values)
        setattr(namespace, self.dest, values)

logger = logging.getLogger()
logging.basicConfig(
    level=logging.WARN,
    format='%(levelname)s\t[%(name)s] %(funcName)s: %(message)s'
    )

parser = argparse.ArgumentParser(
    description='jira 2 zammad migration',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )


parser.add_argument(
    '-l', '--loglevel',
    help='set loglevel',
    type=str,
    choices=[k for k in list(logging.getLevelNamesMapping().keys()) if isinstance(k, str)],
    action=LoggingAction
    )

parser.add_argument(
    '-c','--config',
    nargs='+',
    action="append",
    help='config file',
    required=True
    )

args = parser.parse_args()

# args.config will be a list of lists, so flatten with
configfiles = [item for sublist in args.config for item in sublist]
logger.debug('reading config files ...')
logger.debug(configfiles)
config = hiyapyco.load(configfiles, method=hiyapyco.METHOD_MERGE, usedefaultyamlloader=True)


# init jira
logger.info('jira connection %s ...', config['jira']['baseurl'])
jira = JIRA(
    config['jira']['baseurl'],
    basic_auth=(config['jira']['authuser'],
    config['jira']['authpass']),
    options=config['jira'].get('options', None)
    )

logger.info('... connections established - ready to process issues')


# fetch issue
jissue = jira.issue(f'{config["jira"]["project"]}-1', expand='renderedFields')

print(jissue)
#pprint(vars(jissue))
