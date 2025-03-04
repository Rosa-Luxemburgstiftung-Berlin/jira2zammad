# vim: set fileencoding=utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 smartindent ft=python
# pylint: disable=fixme,invalid-name

"""helper functions for jira 2 zammad migration : issue / ticket"""

import logging
import j2z

logger = logging.getLogger(__name__)

# client connectors
jira = None
zammad = None
mapping = None

def get_zammad_exactmatch(issueidentstr, issueidentfield='id'):
    """as the zammad search via api is not a exact match, we filter the result"""
    zilter = f'{issueidentfield}:{issueidentstr}'
    # filter by the tags applied by default
    for ftag in mapping.get('tags', {}).get('default', []):
        zilter += f' AND tags:{ftag}'
    pages = zammad.ticket.search(zilter)
    rpages = []
    for issue in pages:
        if issue[issueidentfield] == issueidentstr:
            rpages.append(issue)
    return rpages

def get_zammad_issue_count(issueidentstr, issueidentfield='id'):
    """get the number of issues/tickets from zammad by a specific field"""
    pages = get_zammad_exactmatch(issueidentstr, issueidentfield)
    logger.debug(
        'issueidentstr: %s; issueidentfield: %s; pages: %i',
        issueidentstr, issueidentfield, len(pages)
        )
    return len(pages)

def get_zammad_issue(issueidentstr, issueidentfield='id'):
    """try to get a uniq issue/ticket from zammad by a specific field"""
    pages = get_zammad_exactmatch(issueidentstr, issueidentfield)
    if len(pages) == 1:
        for issue in pages:
            return issue
    logger.debug('searching for issue %s returned %i results', issueidentstr, len(pages))
    return None

def get_jira_issue_identifier(issue, identifier):
    """get the value from a jira issue by a identifier"""
    if identifier == "id":
        return issue.id
    if identifier == 'key':
        return issue.key
    return issue.fields.get(identifier)

# state_id:
#    2: open
#    3: pending reminder
#    4: closed
#    7: pending close
#    8: warten auf Klärung
# zam01
#    11: abgelehnt
#    10: bug/known issue
#    13: doppelt
#    4: geschlossen
#    8: in Bearbeitung
#    2: offen
#    12: offen nach Rückfrage
#    3: warten auf Erinnerung
#    9: warten auf Klärung
#    7: warten auf Schließen
#    14: Wiedervorlage
# jira: https://jira2.ber0.rosalux.org:8443/secure/admin/ViewStatuses.jspa
def jira2zammad_transform_value(jiravalue, jirafield):
    """jira value 2 zammad value"""
    if mapping.get('mapping2lower', True):
        jiravalue = jiravalue.lower()
    defaultvalue = mapping.get(jirafield, {}).get('default')
    vmap = mapping.get(jirafield, {}).get('values', {})
    if vmap:
        return vmap.get(jiravalue, defaultvalue)
    return None

# pylint: disable=too-many-return-statements,too-many-branches
def jira2zammad_transform(zammadfieldname, jirafieldname, value):
    """transform the value of a fieled from jira 2 zammad"""
    lvalue = value
    if jirafieldname == 'description' and value:
        lvalue = f'{value[:10]} ...'
    logging.debug('... mapping for %s=%s -> %s', jirafieldname, lvalue, zammadfieldname)
    if value is None:
        return value
    # fix values
    if jirafieldname in ['status']:
        value = value.name.lower()

    # example how to handle label like fields as list
    #if jirafieldname == 'customfield_10703':
    #    value = ', '.join(value)

    # cascading select list
    if jirafieldname in ['customfield_10200', 'customfield_10102']:
        # value.value - holds just the firts entry for nested objects!
        value = f'{value}'

    # example for a custom field cascading select list
    # jira uses ' - ' as a delimiter, and zammad '::'
    #if jirafieldname == 'customfield_10102':
    #    retval = '::'.join(value.split(' - ', 1))

    if jirafieldname in ['issuetype']:
        return value.name.lower()

    if zammadfieldname in ['customer_id', 'owner_id']:
        agent = zammadfieldname == 'owner_id'
        if j2z.user.get_jira_user_ident(value):
            zuser = j2z.user.ensure_zammad_user(
                j2z.user.get_jira_user_ident(value),
                agent=agent
                )
            if zuser:
                return zuser['id']
        return None

    if jirafieldname in mapping and 'values' in mapping[jirafieldname]:
        logging.debug('call generic value mapping fct. for %s=%s', jirafieldname, value)
        return jira2zammad_transform_value(value, jirafieldname)
    return value

def jira2zammad(jiraissue):
    """map jira issue data to a zammad ticket"""
    zicket_data = {}
    body_note = ''  # will be appendet to the body
    # zammad requires a article body, but jira issue description can be empty
    # so we init the article template with triple flyspeck
    zicket_data['article'] = {'body': '...'}
    zicket_data[
            mapping.get('issue', {}).get('key', {}).get('zammad', 'number')
        ] = get_jira_issue_identifier(
                jiraissue,
                mapping.get('issue', {}).get('key', {}).get('jira', 'id')
            )
    zicket_data['created_at'] = jiraissue.get_field('created')
    zicket_data['article']['created_at'] = jiraissue.get_field('created')
    zicket_data['updated_at'] = jiraissue.get_field('updated')
    zicket_data['article']['updated_at'] = jiraissue.get_field('updated')

    for jirafield, zammadfield in mapping.get('issue', {}).get('fields', {}).items():
        if not zammadfield:
            continue
        jiravalue = jiraissue.get_field(jirafield)
        if jirafield == 'description':
            try:
                jiravalue = jiraissue.renderedFields.description
                logger.debug('using rendered description')
            except AttributeError:
                logger.debug('using plain text description')
        zammadvalue = jira2zammad_transform(
            zammadfield,
            jirafield,
            jiravalue
            )
        if zammadvalue is None:
            if zammadfield in ['customer_id', 'owner_id']:
                logger.info('replace %s by zammad connection user ...', zammadfield)
                zammadvalue = zammad.user.me()['id']
                body_note += f'\n\noriginal {zammadfield} : {jiraissue.get_field(jirafield)}'
            else:
                continue
        if zammadfield.startswith('article.'):
            zicket_data['article'][zammadfield.replace('article.', '')] = zammadvalue
        else:
            zicket_data[zammadfield] = zammadvalue
    for zammadfield, zammadvalue in mapping.get('issue', {}).get('constants', {}).items():
        if zammadfield.startswith('article.'):
            zicket_data['article'][zammadfield.replace('article.', '')] = zammadvalue
        else:
            zicket_data[zammadfield] = zammadvalue
    # ensure the ticket reporter is the article creator
    for custfield in ['origin_by_id', 'updated_by_id', 'created_by_id']:
        zicket_data['article'][custfield] =  zicket_data['customer_id']
    # append body_note
    if body_note:
        zicket_data['article']['body'] += body_note
    # ensure we have a minimal body
    if not zicket_data['article']['body'].strip():
        logger.debug('empty body in article: set triple flyspeck content ...')
        zicket_data['article']['body'] = '...'
    return zicket_data
