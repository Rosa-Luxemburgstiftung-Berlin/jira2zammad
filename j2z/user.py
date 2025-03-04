# vim: set fileencoding=utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4 smartindent ft=python
# pylint: disable=fixme,invalid-name,broad-exception-caught

"""helper functions for jira 2 zammad migration : user"""

import os
import logging
import time
import re
import yaml

logger = logging.getLogger(__name__)

# client connectors
jira = None
zammad = None
mapping = None
zuserdamage = None

EMAIL_VALIDATE_PATTERN = r"^\S+@\S+\.\S+$"


class ZUserDamage:
    """store and revert changes made to user objects"""
    def __init__(self, damagefile):
        """init ZUserDamage"""
        self.damagefile = damagefile
        self.damages = {}
        if os.path.exists(self.damagefile):
            with open(self.damagefile, 'r', encoding="utf-8") as df:
                self.damages = yaml.safe_load(df)
                logger.info('restored damages from %s', self.damagefile)

    def registerDamage(self, user_id, change):
        """register a initial state of a user object"""
        update = False
        if not user_id in self.damages:
            self.damages[user_id] = {}
            update = True
        # we register just the initial change
        for k, v in change.items():
            if k not in self.damages[user_id]:
                update = True
                self.damages[user_id][k] = v
        if update:
            self._writedamages()
            logger.debug('changes for %s registered', user_id)

    def _writedamages(self):
        """save the damage file"""
        with open(self.damagefile, 'w', encoding="utf-8") as df:
            damageyaml = yaml.dump(
                    self.damages,
                    indent=2,
                    explicit_start=True,
                    default_flow_style=False,
                    sort_keys=True,
                    allow_unicode=True
                )
            df.write(damageyaml)
            logger.debug('damagefile %s saved ...', self.damagefile)

    def undoDamage(self):
        """revert changes"""
        for uid in list(self.damages):
            changes = self.damages[uid]
            try:
                zuser = zammad.user.find(uid)
                for k, v in changes.items():
                    zuser[k] = v
                zammad.user.update(id=zuser['id'], params=zuser)
                del self.damages[uid]
                logger.debug('user %s : reverted changes', uid)
            except Exception as e:
                logger.error(e)
        if len(self.damages) == 0:
            logger.warning('removing clean damage file %s', self.damagefile)
            os.remove(self.damagefile)
        else:
            logger.warning('saving leftover to damage file %s', self.damagefile)
            self._writedamages()


class UserCache:
    """user cache"""
    def __init__(self, usecache=True):
        """init user cahce"""
        self._usecache = usecache
        self._USERCACHE = {}
    def isEnabled(self):
        """return enabled status"""
        return self._usecache
    def setUsecache(self, usecache):
        """config usage"""
        self._usecache = usecache
        if not self._usecache:
            self._USERCACHE = {}
    def cache(self, userident, zuser):
        """store user in cache"""
        if self._usecache:
            if userident not in self._USERCACHE:
                logger.debug('stored user %s', userident)
            self._USERCACHE[userident] = zuser
    def isCached(self, userident):
        """check if in cache"""
        return userident in self._USERCACHE
    def getUser(self, userident):
        """return user from cache"""
        logger.debug('return %s from cache', userident)
        return self._USERCACHE[userident]


USER_CACHE = UserCache()


def get_jira_user_ident(juser):
    """return value to map user"""
    juseridentfield = mapping.get('user', {}).get('key', {}).get('jira', 'emailAddress')
    if juseridentfield == 'emailAddress':
        if re.match(EMAIL_VALIDATE_PATTERN, juser.emailAddress):
            return juser.emailAddress
        logger.warning('juser %s has a invalid emailAddress "%s"', juser, juser.emailAddress)
        # try to get the mail by key - this should only rarely be necessary
        juser2 = jira.user(id=juser.key)
        if re.match(EMAIL_VALIDATE_PATTERN, juser2.emailAddress):
            return juser2.emailAddress
        logger.warning(
            'jira user %s (id:%s) : unable to get a valid email address',
            juser, juser.key
            )
        return None
    logger.warning('do not now how to handle juseridentfield %s', juseridentfield)
    return None

def ensure_zammad_user(userident, agent=False):
    """ensure we have a user id from zammad"""
    logger.debug('... userident: %s', userident)
    if not userident:
        # pylint: disable=broad-exception-raised
        raise Exception(f'unable to ensure zammad user with invalid userident: "{userident}"')
    if USER_CACHE.isCached(userident):
        user = USER_CACHE.getUser(userident)
        if agent:
            user = ensure_user_agent(userident, user)
            USER_CACHE.cache(userident, user)
        return user
    if get_zammad_user_count(userident) == 0:
        nuser = create_zammad_user(userident, agent)
        zuserdamage.registerDamage(nuser['id'], {'role_ids': [], 'active': False})
        USER_CACHE.cache(userident, nuser)
        return nuser
    user = get_zammad_user(userident, agent)
    USER_CACHE.cache(userident, user)
    return user

def create_zammad_user(userident, agent):
    """create a zammad user - KIS"""
    logger.warning('create zammad user %s', userident)
    zuser_data = {mapping.get('user', {}).get('key', {}).get('zammad', 'email'): userident}
    zuser_data.update(mapping.get('user', {}).get('constants', {}))
    if agent:
        zuser_data['role_ids'] = mapping.get('user', {}).get('agent_role_keys', [2])
    nuster = zammad.user.create(zuser_data)
    # new objects require some time until the can be found, so we have to be patient
    # but if we use the user cache, this is not necessary
    if not USER_CACHE.isEnabled():
        while get_zammad_user_count(userident) == 0:
            logger.debug('waiting for user %s to appear ...', userident)
            time.sleep(1)
    return nuster

def get_zammad_user_exactmatch(userident):
    """filter the user search for exact match"""
    useridentfield = mapping.get('user', {}).get('key', {}).get('zammad', 'email')
    ruser_pages = []
    user_pages = zammad.user.search(f'{useridentfield}:{userident}')
    logger.debug('search zammad user %s %s ...', useridentfield, userident)
    for user in user_pages:
        logger.debug(
            'check zammad user "%s" =?= "%s" ...',
            user[useridentfield].lower(), userident.lower()
            )
        if user[useridentfield].lower() == userident.lower():
            ruser_pages.append(user)
            logger.debug('check zammad user %s : OK, matches', userident)
    logger.debug('returning %i matches for %s', len(ruser_pages), userident)
    return ruser_pages

def get_zammad_user_count(userident):
    """get number of user from zammad by email"""
    user_pages = get_zammad_user_exactmatch(userident)
    return len(user_pages)

def ensure_user_agent(userident, user):
    """promote a user to agent if required"""
    # pylint: disable=line-too-long
    if not all(item in user['role_ids'] for item in mapping.get('user', {}).get('agent_role_keys', [2])):
        logger.info(
            'user %s (%i) will be promoted as agent! %s != %s',
            userident, user['id'],
            sorted(user['role_ids']),
            sorted(mapping.get('user', {}).get('agent_role_keys', [2]))
            )
        zuserdamage.registerDamage(user['id'], {'role_ids': user['role_ids']})
        user['role_ids'] = list(set(
            user.get('role_ids', []) + mapping.get('user', {}).get('agent_role_keys', [2])
            ))
        logger.debug(
            'new role IDs for user %s (id:%s): %s',
            userident, user['id'], user['role_ids']
            )
        # as long as the roles key is present,
        # the update will NOT be performed as expected!
        user.pop('roles', None)
        zammad.user.update(id=user['id'], params=user)
    return user

def get_zammad_user(userident, agent=False):
    """try to get a uniq user from zammad by email"""
    logger.debug('search zammad user %s ...', userident)
    user_pages = get_zammad_user_exactmatch(userident)
    if len(user_pages) != 1:
        logger.debug('searching for user %s returned %i results', userident, len(user_pages))
    if len(user_pages) > 0:
        for user in user_pages:
            if len(user_pages) > 1:
                logger.debug('returning first match for user %s!', userident)
            if not user['active']:
                logger.debug('user %s (%i) will be activated!', userident, user['id'])
                zuserdamage.registerDamage(user['id'], {'active': False})
                user['active'] = True
                zammad.user.update(id=user['id'], params=user)
            if agent:
                user = ensure_user_agent(userident, user)
            logger.debug('... found user id %i for %s', user['id'], userident)
            return user
    return None
