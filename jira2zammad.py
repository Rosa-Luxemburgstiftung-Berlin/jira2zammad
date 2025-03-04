#! /usr/bin/env python3
# vim: set fileencoding=utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 smartindent ft=python
# pylint: disable=fixme,missing-module-docstring,missing-class-docstring,wrong-import-position

import os
import sys
import logging
import time
import argparse
import urllib3
import hiyapyco

# in case we have the jira and zammad as git submodule
_BASEDIR_ = os.path.dirname(os.path.abspath(__file__))
for submodule in ['jira', 'zammad_py']:
    sys.path.append(os.path.join(_BASEDIR_, submodule))
# if you use submodules, you must call pylint using
# PYTHONPATH=jira/:zammad_py/ pylint jira2zammad.py ...

# https://jira.readthedocs.io/api.html#jira.client.JIRA
from jira import JIRA
# https://zammad-py.readthedocs.io/en/latest/usage.html
from zammad_py import ZammadAPI

# our pimpy helper modules
import j2z.user
import j2z.issue
import j2z.comment
import j2z.tags
import j2z.attachment
import j2z.issuelink

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
    format='%(asctime)s %(levelname)-8s\t[%(name)s] %(funcName)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
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

parser.add_argument(
    '-d','--damagefile',
    type=str,
    help='file to store the changes made to users',
    default='/var/tmp/jira2zammad-damage-done.yml'
    )

parser.add_argument(
    '-D','--continuedamagefile',
    help='continue using a existing damagefile',
    action="store_true"
    )

parser.add_argument(
    '-u','--noundodamage',
    help='skip undo changes to user objects',
    action="store_true"
    )

parser.add_argument(
    '-j','--jiraissue',
    nargs='+',
    action="append",
    help='handle just the listed jira issue(s) for testing',
    )

parser.add_argument(
    '-s','--startat',
    type=int, default=0,
    help='start at jira search page ... ',
    )

parser.add_argument(
    '-m','--maxresults',
    type=int, default=50,
    help='max results per jira search page ... ',
    )

parser.add_argument(
    '-U','--nousercache',
    action="store_true",
    help='disable using the internal cache for users ... ',
    )

args = parser.parse_args()

# args.config will be a list of lists, so flatten with
configfiles = [item for sublist in args.config for item in sublist]
logger.debug('reading config files ...')
logger.debug(configfiles)
config = hiyapyco.load(
    configfiles,
    method=hiyapyco.METHOD_MERGE,
    usedefaultyamlloader=True,
    loglevel=logging.ERROR)

if os.path.exists(args.damagefile) and not args.continuedamagefile:
    sys.exit(f'damagefile {args.damagefile} exists!')

zuserdamage = j2z.user.zuserdamage = j2z.user.ZUserDamage(args.damagefile)

# init jira
logger.info('jira connection %s ...', config['jira']['baseurl'])
jira = JIRA(
    config['jira']['baseurl'],
    basic_auth=(config['jira']['authuser'],
    config['jira']['authpass']),
    options=config['jira'].get('options', None)
    )

# init zammad
logger.info('zammad connection %s ...', config['zammad']['baseurl'])
zammad = ZammadAPI(
    url=config['zammad']['baseurl'],
    username=config['zammad'].get('authuser', None),
    password=config['zammad'].get('authpass', None),
    http_token=config['zammad'].get('authtoken', None),
    )
zammad.session.verify = config['zammad'].get('verify', True)  # ssl verification

logger.info('... connections established - ready to process issues')

# propagate connector to modules
# FIXME: q&d - improve
j2z.issue.jira = j2z.user.jira = j2z.comment.jira = j2z.tags.jira = j2z.issuelink.jira =  jira
j2z.issue.zammad = j2z.user.zammad = j2z.comment.zammad = j2z.tags.zammad = j2z.issuelink.zammad = j2z.attachment.zammad = zammad  # pylint: disable=line-too-long
j2z.issue.mapping = j2z.user.mapping = j2z.comment.mapping = j2z.tags.mapping = j2z.attachment.mapping = config['mapping']  # pylint: disable=line-too-long
j2z.issuelink.config = config

if args.nousercache:
    j2z.user.USER_CACHE.setUsecache(False)

# fetch issues
pjql = 'project = {} ORDER BY key ASC'.format(config['jira']['project'])  # pylint: disable=consider-using-f-string
if args.jiraissue:
    jirraissues = [item for sublist in args.jiraissue for item in sublist]
    jirraissuesjqllist = '({})'.format(','.join(jirraissues))  # pylint: disable=consider-using-f-string,invalid-name
    pjql = f'key in {jirraissuesjqllist} ORDER BY key ASC'
    args.maxresults = 1
IS_LAST = False
START_AT = args.startat
MAX_RESULTS = args.maxresults
logger.info('jql: %s', pjql)
while not IS_LAST:
    logger.warning('loop %i issue starting from %i', MAX_RESULTS, START_AT)
    # pylint: disable=invalid-name
    resList = jira.search_issues(
        jql_str=pjql,
        startAt=START_AT,
        maxResults=MAX_RESULTS,
        expand='renderedFields'
        )
    # isLast : Note that this property is not returned for all operations.
    if not resList:
        IS_LAST = True
        logger.info('reached end of issue loop!')
        break
    IS_LAST = resList.isLast
    START_AT = START_AT + MAX_RESULTS
    for single_issue in resList:  # pylint: disable=not-an-iterable
        logger.info('parse jira issue %s : %s', single_issue.key, single_issue.fields.summary)
        jidentfield = config['mapping']['issue']['key'].get('jira', 'id')
        jident = j2z.issue.get_jira_issue_identifier(single_issue, jidentfield)
        zidentfield = config['mapping']['issue']['key'].get('zammad', 'number')
        logger.debug(
            'jidentfield: %s; jident: %s; zidentfield: %s',
            jidentfield, jident, zidentfield
            )
        if j2z.issue.get_zammad_issue_count(jident, issueidentfield=zidentfield) > 0:
            logger.warning(
                'jira issue %s=%s already exists in zammad (%s=%s)',
                jidentfield, jident, zidentfield, jident
                )
            continue
        try:
            zicket_data = j2z.issue.jira2zammad(single_issue)
        except Exception as zicketdataexception:  # pylint: disable=broad-exception-caught
            #import traceback
            #traceback.print_exc()
            logger.error(
                'unable to translate data from jira 2 zammad for %s : %s',
                jident, zicketdataexception
                )
            continue
        # attachments:
        # the main problem here is, that attachments in zammad are bound to articles
        # and in jira to issues with optional occurence in comments as link or inline
        jatchments = j2z.attachment.JAtchments(
            single_issue.fields.attachment,
            single_issue.key,
            config
            )
        # attachments can be in the description too
        if zicket_data.get('article', {}).get('body'):
            attamatched, attachments, body = jatchments.check_attachments_in_article(
                    zicket_data['article']['body'],
                    single_issue.get_field('reporter')
                )
            if attamatched:
                logger.info(
                    'issue %s : updated description because of attachments (%i)',
                    jident, len(attachments)
                    )
                zicket_data['article']['body'] = body
                for attachment in attachments:
                    zattchment = j2z.attachment.jira2zammad(attachment)
                    zicket_data['article']['attachments'].append(zattchment)
        # TODO: mention in comments and description
        # <a class="user-hover" href="https://<JIRA>/secure/ViewProfile.jspa?name=<LOGIN>"><SNAME, FNAME></a>  # pylint: disable=line-too-long
        # <a href=\"https://<ZAMMAD>/#user/profile/<ID>\" data-mention-user-id=\"<ID>\"><FNAME SNAME></a>      # pylint: disable=line-too-long
        logger.debug('zicket_data ...')
        logger.debug(zicket_data)
        try:
            zicket = zammad.ticket.create(zicket_data)
            logger.warning('jira issue %s created as zammad ticket %i ...', jident, zicket['id'])
            # in order to find the matching ticket we need to appyl the tags if configured
            for identtag in config['mapping'].get('tags', {}).get('default', []):
                zammad.ticket_tag.add(zicket['id'], identtag)
            while j2z.issue.get_zammad_issue_count(jident, issueidentfield=zidentfield) == 0:
                logger.debug('waiting for new zammad ticket %s to appear ...', jident)
                time.sleep(1)
        except Exception as zicketexception:  # pylint: disable=broad-exception-caught
            logger.error('unable to create zammad issue for %s : %s', jident, zicketexception)
            logger.error(zicket_data)
            continue
        clist = jira.comments(single_issue.id, 'renderedBody,properties')
        for jiracomment in clist:
            logger.debug('... jiracomment %s', jiracomment)
            zarticle = {}
            zarticle = j2z.comment.jira2zammad(zicket['id'], jiracomment)
            # attachments in comment
            if zarticle.get('body'):
                attamatched = False
                attamatched, attachments, body = jatchments.check_attachments_in_article(zarticle['body'], jiracomment.author)  # pylint: disable=line-too-long
                if attamatched:
                    logger.info(
                        'issue %s : updated comment "%s ..." because of attachments (%i)',
                        jident, body[:10], len(attachments)
                        )
                    zarticle['body'] = body
                    for attachment in attachments:
                        logger.debug(
                            'issue %s : comment "%s ..." - append attachment %s',
                            jident, body[:10], attachment.filename
                            )
                        zattchment = j2z.attachment.jira2zammad(attachment)
                        zarticle['attachments'].append(zattchment)
            #logger.debug('zarticle updated ... attachments: %s', zarticle.get('attachments'))
            #logger.debug('zarticle ...')
            #logger.debug(zarticle)
            try:
                zart = zammad.ticket_article.create(zarticle)
                logger.info('ticket_article created: %i', zart['id'])
            except Exception as zarticleexception:  # pylint: disable=broad-exception-caught
                logger.error('unable to create zammad comment: %s', zarticleexception)
                logger.error(zarticle)
                logger.error(jiracomment.id)
        # all attachements that are left over as internal comment
        for attachment in jatchments.get_attachments():
            logger.debug('handle remaining attachment %s', attachment.filename)
            zarticle = j2z.attachment.jiraattachement2comment(zicket['id'], attachment)
            try:
                zart = zammad.ticket_article.create(zarticle)
                logger.info('remaining attachments as ticket_article created: %i', zart['id'])
            except Exception as zarticleexception:  # pylint: disable=broad-exception-caught
                logger.error(
                    'unable to create zammad article for attachment %s: %s',
                    attachment.filename, zarticleexception
                    )
                logger.error(zarticle)
        # labels + components -> tags
        j2z.tags.jira2zammad(zicket['id'], single_issue)
        logger.warning('jira issue %s migrated as zammad ticket %i', jident, zicket['id'])

# postprocessing: issue links
# issue links can only be processed after all issues are imported
IS_LAST = False
START_AT = args.startat
MAX_RESULTS = args.maxresults
logger.warning('start postprocessing: issuelinks ...')
while not IS_LAST:
    logger.warning('issuelinks : loop %i issues starting from %i', MAX_RESULTS, START_AT)
    # pylint: disable=invalid-name
    resList = jira.search_issues(
        jql_str=pjql,
        startAt=START_AT,
        maxResults=MAX_RESULTS,
        expand='renderedFields'
        )
    # isLast : Note that this property is not returned for all operations.
    if not resList:
        IS_LAST = True
        logger.info('issuelinks : reached end of issue loop!')
        break
    IS_LAST = resList.isLast
    START_AT = START_AT + MAX_RESULTS
    for single_issue in resList:  # pylint: disable=not-an-iterable
        j2z.issuelink.jira2zammad(single_issue)
logger.warning('postprocessing: issuelinks done')


# revert the changes we have made to users
if not args.noundodamage:
    logger.warning('postprocessing: start undoDamage ...')
    zuserdamage.undoDamage()

logger.warning('all done! abba zaba go-zoom babbette baboon')
