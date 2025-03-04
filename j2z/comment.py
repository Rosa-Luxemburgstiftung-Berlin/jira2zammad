# vim: set fileencoding=utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 smartindent ft=python
# pylint: disable=fixme,invalid-name,unused-import

"""helper functions for jira 2 zammad migration : issue / ticket comments"""

import logging
import j2z
from jira import JIRAError

logger = logging.getLogger(__name__)

jira = None
zammad = None
mapping = None

# https://jira.readthedocs.io/api.html#jira.client.JIRA.comments
#
# jira comment props
#    {
#      "author": {
#        "accountId": ...
#        "active": false,
#        "displayName": ...
#        "emailAddress': ...
#        "self": ...
#      },
#      "body": ...
#      "created": ...
#      "id": ...
#      "self": ...
#      "updateAuthor": {
#        "accountId": ...
#        "active": false,
#        "displayName": ...
#        "emailAddress': ...
#        "self": ...
#      },
#      "updated": ...
#      "visibility": {
#        "identifier": ...
#        "type": ...
#        "value": ...
#      }
#    }
#
# zammad article params create
#{
#    "from": "admin -",
#    "to": "",
#    "cc": "",
#    "subject": "",
#    "body": "test comment",
#    "content_type": "text/html",
#    "ticket_id": 420,
#    "type_id": 10,
#    "sender_id": 1,
#    "internal": true,
#    "in_reply_to": "",
#    "form_id": "1ba9ad39-1f25-445e-bbb9-9982e3ba39cb",
#    "subtype": ""
#}
# zammad article
# {
#    "id": 4788,
#    "ticket_id": 420,
#    "type_id": 10,
#    "sender_id": 1,
#    "from": "admin -",
#    "to": "",
#    "cc": "",
#    "subject": "",
#    "reply_to": null,
#    "message_id": null,
#    "message_id_md5": null,
#    "in_reply_to": "",
#    "content_type": "text/html",
#    "body": "test comment",
#    "internal": true,
#    "preferences": {
#
#    },
#    "updated_by_id": 3,
#    "created_by_id": 3,
#    "origin_by_id": null,
#    "created_at": "2025-01-23T05:31:54.802Z",
#    "updated_at": "2025-01-23T05:31:54.802Z",
#    "attachments": [],
#    "created_by": "zammad",
#    "updated_by": "zammad",
#    "type": "note",
#    "sender": "Agent",
#    "time_unit": null
#  }
# t420 = zammad.ticket.find(420)
# print(t420)
# ta = zammad.ticket.articles
# print(ta)
#
# a = {
#    "ticket_id": 420,
#    "type_id": 10,
#    #"sender_id": 55,
#    "origin_by_id": 55,
#    # "from": "en",
#    # "to": "",
#    # "cc": "",
#    "subject": "",
#    #"reply_to": null,
#    #"message_id": null,
#    #"message_id_md5": null,
#    #"in_reply_to": "",
#    "content_type": "text/html",
#    "body": "Test Comment in the past",
#    "internal": True,
#    #"preferences": {},
#    "updated_by_id": 55,
#    "created_by_id": 55,
#    "created_at": "2025-01-20T17:45:21.813Z",
#    "updated_at": "2025-01-20T17:45:21.813Z",
#    #"attachments": [],
#    #"created_by": "zerwes",
#    #"updated_by": "zerwes",
#    "type": "note",
#    #"sender": "Agent",
#    #"time_unit": null
#  }
# za = zammad.ticket_article.create(params=a)

def jira2zammad(zammad_id, jiracomment):
    """transform a jira comment into a zammad article"""
    zarticle = {}
    zarticle = mapping['comment'].get('constants', {})
    zarticle['ticket_id'] = zammad_id
    zarticle['attachments'] = []
    # we prefere renderedBody if expanded
    try:
        zarticle['body'] = jiracomment.renderedBody
    except AttributeError:
        zarticle['body'] = jiracomment.body
    #jiracomment.author.emailAddress
    juserident = j2z.user.get_jira_user_ident(jiracomment.author)
    if juserident:
        zuser = j2z.user.ensure_zammad_user(juserident)
    else:
        zuser = zammad.user.me()
        zarticle['body'] += f'\n\noriginal author: {jiracomment.author}'
    if zuser:
        for zuseridfield in ['origin_by_id', 'updated_by_id', 'created_by_id']:
            zarticle[zuseridfield] = zuser['id']
    for dfield in ['created_at', 'updated_at']:
        zarticle[dfield] = jiracomment.updated
    # internal commment?
    zarticle['internal'] = False
    for cprop in jiracomment.properties:
        if 'sd.public.comment' == cprop.key:
            if isinstance(cprop.value.internal, bool):
                zarticle['internal'] = cprop.value.internal
            elif cprop.value.internal.lower() == 'true':
                zarticle['internal'] = True
    return zarticle
