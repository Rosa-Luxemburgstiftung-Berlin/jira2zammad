# vim: set fileencoding=utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 smartindent ft=python
# pylint: disable=fixme,invalid-name,line-too-long,too-many-branches

"""helper functions for jira 2 zammad migration : issuelinks / ticket"""

import logging
import j2z

logger = logging.getLogger(__name__)

# client connectors
jira = None
zammad = None
config = None

# https://www.atlassian.com/blog/developer/jira-issue-linking-model
# https://docs.zammad.org/en/latest/api/ticket/links.html
# i.e. issue X-59725 has:
#   inwardIssues:
#       relates to X-59204
#       relates to X-59672
#       is subtask of X-59672
# in the ourward view this will be:
#   X-59204 has relates to X-59725
#   X-59672 has relates to X-59725
#   X-59862 has is parent task of X-59725
# so in most cases just considering one direction should be sufficient
# but in order to be sure we do not miss a link, we can consider both

def get_mapped_issuelink(jissuelink):
    """
    mapp a link from jira 2 zammad
    return zammad target ticket, zammad link type
    """
    logger.debug(jissuelink)
    dir2consider = config.get('issuelinks', {}).get('directions', [])
    #logger.debug(dir2consider)
    target_issue_key = None
    link_type = None
    mapped_type = None
    jidentfield = config['mapping']['issue']['key'].get('jira', 'id')
    if config.get('issuelinks', {}).get('match_all_unmapped_to_normal', False):
        mapped_type = 'normal'
    if 'outwardIssue' in dir2consider:
        logger.debug('... check outwardIssue ...')
        if hasattr(jissuelink, 'outwardIssue'):
            if jidentfield == 'key':
                target_issue_key = jissuelink.outwardIssue.key
            elif jidentfield == 'id':
                target_issue_key = jissuelink.outwardIssue.id
            else:
                logger.warning('issuelinks require key or id as mapping.issue.key.jira cfg')
                return None, None
            link_type = jissuelink.type.outward
    if not target_issue_key and 'inwardIssue' in dir2consider:
        logger.debug('... check inwardIssue ...')
        if hasattr(jissuelink, 'inwardIssue'):
            if jidentfield == 'key':
                target_issue_key = jissuelink.inwardIssue.key
            elif jidentfield == 'id':
                target_issue_key = jissuelink.inwardIssue.id
            else:
                logger.warning('issuelinks require key or id as mapping.issue.key.jira cfg')
                return None, None
            link_type = jissuelink.type.inward
    logger.debug('... %s -> %s', link_type, target_issue_key)
    if target_issue_key:
        for ztype, jtype in config.get('issuelinks', {}).get('mapping', {}).items():
            if jtype == link_type:
                mapped_type = ztype
                break
        zidentfield = config['mapping']['issue']['key'].get('zammad', 'number')
        target_zicked = j2z.issue.get_zammad_issue(target_issue_key, zidentfield)
        return target_zicked, mapped_type
    return None, None

def jira2zammad(issue):
    """transfer all issuelinks of a jira issue to zammad"""
    logger.info(
        'parse jira issue %s : %s',
        issue.key, issue.fields.summary
        )
    jidentfield = config['mapping']['issue']['key'].get('jira', 'id')
    jident = j2z.issue.get_jira_issue_identifier(issue, jidentfield)
    zidentfield = config['mapping']['issue']['key'].get('zammad', 'number')
    zicket = j2z.issue.get_zammad_issue(jident, issueidentfield=zidentfield)
    if not zicket:
        logger.error(
            'unable to find matching ticket for issue %s=%s',
            zidentfield, jident
            )
        return False
    for ili in issue.fields.issuelinks:
        target_zicket, ticketlinktype = get_mapped_issuelink(ili)
        logger.debug(
            '... process jira link %s ... %s -> %s',
            ili, ticketlinktype, target_zicket
            )
        if target_zicket and ticketlinktype:
            logger.debug(
                'create zammad ticket link %s -> %s of type %s',
                zicket['number'], target_zicket['id'], ticketlinktype
                )
            try:
                zammad.link.add(
                    target_zicket['id'],  # link_object_target must be the ID
                    zicket['number'],     # link_object_source_number has to be the ticket number
                    link_type=ticketlinktype
                    )
            except Exception as zinke:  # pylint: disable=broad-exception-caught
                if str(zinke.args[0]) == '{"error":"This object already exists.","error_human":"This object already exists."}':
                    logger.debug('... duplicated link ... %s', zinke)
                else:
                    logger.error(
                        'error creating zammad link  %s -> %s of type %s : %s',
                        zicket['number'], target_zicket['id'], ticketlinktype, zinke
                        )
    return True
