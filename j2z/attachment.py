# vim: set fileencoding=utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 smartindent ft=python
# pylint: disable=fixme,invalid-name

"""helper functions for jira 2 zammad migration : issue / ticket attachments"""

import logging
import re
import base64
import urllib.parse
import j2z

logger = logging.getLogger(__name__)

zammad = None
mapping = None

def jira2zammad(attachment):
    """transform a attachment from jira for zammad upload"""
    zattachment = {}
    zattachment['filename'] = attachment.filename
    zattachment['mime-type'] = attachment.mimeType
    zattachment['data'] = base64.b64encode(attachment.get()).decode("utf-8")
    #logger.debug('... zattachment data type: %s', type(zattachment['data']))
    return zattachment

def jiraattachement2comment(zammad_id, attachment):
    """create a comment from a attachment"""
    logger.debug('... zammad_id %s, attachment %s', zammad_id, attachment)
    zarticle = mapping['comment'].get('constants', {}).copy()
    zarticle['ticket_id'] = zammad_id
    juserident = zuser = None
    try:
        juserident = j2z.user.get_jira_user_ident(attachment.author)
        zuser = j2z.user.ensure_zammad_user(juserident)
        logger.debug('... zammad user for attachment: %s', zuser)
    except Exception:  # pylint: disable=broad-exception-caught
        zuser = zammad.user.me()
    try:
        zarticle['body'] = f'{attachment.filename} attached by {attachment.author}'
    except AttributeError:
        zarticle['body'] = f'{attachment.filename} attached by unknown'
    if zuser:
        for zuseridfield in ['origin_by_id', 'updated_by_id', 'created_by_id']:
            zarticle[zuseridfield] = zuser['id']
    for dfield in ['created_at', 'updated_at']:
        zarticle[dfield] = attachment.created
    zarticle['internal'] = True
    zarticle['attachments'] = [j2z.attachment.jira2zammad(attachment)]
    return zarticle

class JAtchments:
    """jira attachments helper class"""
    def __init__(self, jiraattachments, jkey, config):
        """attachments of a jira issue"""
        self.attachments = []
        for ja in jiraattachments:
            try:  # in rare cases some attachments might have no author
                logger.debug('attachment %s by %s', ja.filename, ja.author)
            except AttributeError:
                logger.debug('attachment %s with missing author', ja.filename)
            self.attachments.append(ja)
        self.config = config
        self.attachmentconfig = config['mapping'].get('attachment', {}).copy()
        self.jira_issue = jkey
        logger.debug('created instance of JAtchments for %s', self.jira_issue)

    def get_attachments(self):
        """return attachments"""
        return self.attachments

    def _format(self, fstr, attachment):
        """format for re - parts will be re.escape'd"""
        filenameurl = urllib.parse.quote_plus(attachment.filename)
        filenameunq = urllib.parse.unquote_plus(attachment.filename)
        return fstr.format(
                    jirabaseurl=re.escape(self.config['jira']['baseurl']),
                    jiraissue=re.escape(self.jira_issue),
                    filename=re.escape(attachment.filename),
                    filenameurl=re.escape(filenameurl),
                    filenameunq=re.escape(filenameunq),
                    attachmenturl=re.escape(attachment.content),
                    attachmentid=re.escape(attachment.id)
                )

    # pylint: disable=too-many-locals,too-many-branches
    def check_attachments_in_article(self, articletext, author):
        """detect if attachments are reference in the article text"""
        attachment_matches = []
        if not author:
            return (False, attachment_matches, articletext)
        articleauthor = j2z.user.get_jira_user_ident(author)
        if not articleauthor:
            return (False, attachment_matches, articletext)
        articleauthor = articleauthor.lower()
        if articletext:  # can be None
            logger.debug('article "%s ..." by %s', articletext[:10], articleauthor)
        else:
            logger.debug('article "%s" by %s', articletext, articleauthor)
        matched = False
        for attachment in self.attachments:
            amatched = False
            attachmentauthor = None
            try:
                attachmentauthor = j2z.user.get_jira_user_ident(attachment.author).lower()
            except AttributeError:
                pass
            if not articleauthor == attachmentauthor:
                logger.debug(
                    '%s - attachmentauthor %s is not matching',
                    attachment.filename, attachmentauthor
                    )
                continue
            logger.debug(
                '... check attachment %s by %s',
                attachment.filename, attachmentauthor
                )
            for matchre in self.attachmentconfig.get('matchlink', []):
                regexmatcher = self._format(matchre, attachment)
                logger.debug('... matchlink %s', regexmatcher)
                if re.search(regexmatcher, articletext):
                    logger.debug('match: matchlink "%s" ...', regexmatcher)
                    attachment_matches.append(attachment)
                    self.attachments.remove(attachment)
                    # we replace the link with the name of the attachment
                    articletext = re.sub(regexmatcher, attachment.filename, articletext)
                    matched = amatched = True
                    #logger.debug(articletext)
                    break
            if not amatched:
                for matchre in self.attachmentconfig.get('matchinline', []):
                    regexmatcher = self._format(matchre, attachment)
                    logger.debug('... matchinline "%s" ...', regexmatcher)
                    if re.search(regexmatcher, articletext):
                        logger.debug('match: matchinline %s', regexmatcher)
                        self.attachments.remove(attachment)
                        # inline img  <img src="data:image/png;base64,...">
                        mimetype = attachment.mimeType
                        b64 = base64.b64encode(attachment.get()).decode("utf-8")
                        inlineres = f'<div><img src="data:{mimetype};base64,{b64}"></div><br />'
                        articletext = re.sub(regexmatcher, inlineres, articletext)
                        matched = amatched = True
                        #logger.debug(articletext)
                        break
            if amatched:
                for matchre, replace in self.attachmentconfig.get('replace', {}).items():
                    regexmatcher = self._format(matchre, attachment)
                    replacef = self._format(replace, attachment)
                    logger.debug(
                        '... replace "%s" w/ "%s" ....',
                        regexmatcher, replacef
                        )
                    articletext = re.sub(regexmatcher, replacef, articletext)
        #logger.debug(attachment_matches)
        #logger.debug(articletext)
        return (matched, attachment_matches, articletext)
