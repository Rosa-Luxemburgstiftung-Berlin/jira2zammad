# vim: set fileencoding=utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 smartindent ft=python
# pylint: disable=fixme,invalid-name,unused-import

"""helper functions for jira 2 zammad migration : issue / ticket tags"""

import re
import logging
import j2z
from jira import JIRAError

logger = logging.getLogger(__name__)

jira = None
zammad = None
mapping = None

def jira2zammad(zammad_id, jiraissue):
    """map labels and componentes form a jira issue to zammad tags"""
    tags = mapping.get('tags', {}).get('default', []).copy()
    for jc in jiraissue.get_field('components'):
        tag = jc.name.capitalize()
        logger.debug('%s : component %s -> tag %s', jiraissue.key, jc.name, tag)
        if tag not in tags:
            tags.append(tag)
    for label in jiraissue.get_field('labels'):
        logger.debug('%s : label %s ...', jiraissue.key, label)
        # do not migrate labels with underscore
        if '_' in label:
            continue
        # remove garbage
        label = re.sub(r'[^a-zA-Z0-9]', '', label)
        if len(label) > 3:
            tag = label.capitalize()
        else:
            tag = label.upper()
        if '-' in label:
            tag = '-'.join(l.capitalize() for l in label.split('-'))
        if tag not in tags:
            tags.append(tag)
        logger.debug('%s : label %s -> tag %s', jiraissue.key, label, tag)
    logger.debug('issue : %s ... final tags:', jiraissue.key)
    logger.debug(tags)
    for tag in tags:
        zammad.ticket_tag.add(zammad_id, tag)
