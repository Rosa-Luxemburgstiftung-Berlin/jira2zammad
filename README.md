# jira2zammad
python script for Jira -> Zammad migration using the API

## about

**This is not a ready-to-use software!**

**This was not written with code beauty in mind.**

**This is no elegant and no efficient code.**

**This was just written straight forward: one shot, kick'n'rush, disposable software.**

**We do not offer any support, only an opportunity that you can take yourself.**

:exclamation: **No warranty!** :exclamation:

## TL;DR

The [RLS](https://www.rosalux.de/) [IT](https://github.com/Rosa-Luxemburgstiftung-Berlin) jira2zammad migration story ...

Well, after using [Atlassian Jira](https://www.atlassian.com/software/jira) for a long time,
the license changes in the last years forced us to migrate to other software.

We decided to go for [zammad](https://zammad.com/) (and [openproject](https://www.openproject.org/), but that is another story).

In our old Jira server instance, we had several projects, the biggest one with round about 44000 issues.
As these might contain valuable information, we decided do preserve this for the future, and migrate them into our new zammad instance.

While looking for a option, it seemed the official way to do this, was this: https://zammad.com/en/product/features/skyvia ...

Well, we opt in, and rented one of the required components each from skyvia and zammad.

But the path to the migration was far from being straight forward ... awkward to configure, hard to debug etc.

But we persisted, until we realized more and more obstacles.

And so we decided to do our own thing!

We looked for existing python bindings for the jira and zammad API, extended them, created some PR
(yes, we do not just consume open source here @ [RLS IT](https://github.com/Rosa-Luxemburgstiftung-Berlin), we try to live it),
and started a small project.

First of all: we tested on a cloned instance of our existing zammad setup!

Step by step we migrated single issues, fixing more and more fields and settings.
If the result was not satisfactory, we removed the ticket and started all over again ...
```
zammad run rails r 'Ticket.find(ZAMMAD_TICKET_ID).destroy'
```
And finally we had a working setup, moving about **44 thousand issues** and more then **1500 user objects** from jira to zammad,
preserving timestamps, attachments, components and labels as tags, ...

The run including re-indexing took about **70 hours**, but as it is a one time task, this was OK for us.

And here we publish the script, with the restrictions already mentioned ...

If it is of use for you: just take it and use it (under the terms of the [AGPL-3.0 license](https://www.gnu.org/licenses/agpl-3.0.de.html))

Good luck!

## features

Migrate:

  * issue / ticket
  * user
  * preserve timestamps of issues / tickets / comments etc.
  * preserve users for author/assignee/comments/attachments ...
  * attachments (as files or inline)
  * jira components and labels to tags
  * configurable field mapping
  * ...

## install

```
git clone https://github.com/Rosa-Luxemburgstiftung-Berlin/jira2zammad.git
cd jira2zammad
```

## requirements

### pip

**Note**: as long as the [PR for tags](https://github.com/joeirimpan/zammad_py/pull/254) is not published as a new release of *zammad-py*,
the pip variant will not work as expected! The current 3.0.0 version of *zammad-py* is missing the required feature.
So at least *zammad-py* must be installed as a git submodule.

```
pip install -r jira2zammad-requirements.txt
```

### deb

```
apt install python3-requests python3-packaging python3-typing-extensions
```

#### hiyapyco

please follow the instructions from https://github.com/zerwes/hiyapyco#debian-packages

## zammad-py and jira as git submodules

in the jira2zammad directory, run

```
# zammad-py
git submodule add https://github.com/joeirimpan/zammad_py.git

# jira
git submodule add https://github.com/pycontribs/jira.git
# or w/ some not yet merged PR
git submodule add --branch CommentProperty https://github.com/Rosa-Luxemburgstiftung-Berlin/jira.git
```

**Note**: other versions of *zammad-py* or *jira* that have been installed via pip or the local package management must be removed in order to use the local submodules.

## run

### command line args

```
± ./jira2zammad.py -h
usage: jira2zammad.py [-h] [-l {CRITICAL,FATAL,ERROR,WARN,WARNING,INFO,DEBUG,NOTSET}] -c CONFIG [CONFIG ...] [-d DAMAGEFILE] [-D] [-u] [-j JIRAISSUE [JIRAISSUE ...]] [-s STARTAT] [-m MAXRESULTS] [-U]

jira 2 zammad migration

options:
  -h, --help            show this help message and exit
  -l {CRITICAL,FATAL,ERROR,WARN,WARNING,INFO,DEBUG,NOTSET}, --loglevel {CRITICAL,FATAL,ERROR,WARN,WARNING,INFO,DEBUG,NOTSET}
                        set loglevel (default: None)
  -c CONFIG [CONFIG ...], --config CONFIG [CONFIG ...]
                        config file (default: None)
  -d DAMAGEFILE, --damagefile DAMAGEFILE
                        file to store the changes made to users (default: /var/tmp/jira2zammad-damage-done.yml)
  -D, --continuedamagefile
                        continue using a existing damagefile (default: False)
  -u, --noundodamage    skip undo changes to user objects (default: False)
  -j JIRAISSUE [JIRAISSUE ...], --jiraissue JIRAISSUE [JIRAISSUE ...]
                        handle just the listed jira issue(s) for testing (default: None)
  -s STARTAT, --startat STARTAT
                        start at jira search page ... (default: 0)
  -m MAXRESULTS, --maxresults MAXRESULTS
                        max results per jira search page ... (default: 50)
  -U, --nousercache     disable using the internal cache for users ... (default: False)
```

### cfg

#### secrets
configure seecrets in `jira2zammad-secrets.yml` or in `jira2zammad.yml`

```yaml
---
# example secrets for jira2zammad.py
jira:
  baseurl: https://jira.example.org:8443/
  authuser: jira@example.org
  authpass: T0PSecret # token or pass
zammad:
  baseurl: https://zammad.example.org/api/v1/
  #authtoken: ....
  authuser: zammad
  authpass: AbbaZabbaSecret

```

**note**:

  * the zammad admin user needs agent rights in order to create issues
  * the jira user must have at least full read access to the project in question


#### cfg mapping

Most mappings can be configured in `jira2zammad.yml` (`mapping:` key).

Some extra handling can be coded in `j2z/issue.py:jira2zammad_transform`.
There are some examples how to handle label like fields and cascading select lists.

### run import

#### prepare zammad instance
```
# zammad needs to be in import mode in order to allow setting dates in the past
zammad run rails r 'Setting.set("import_mode", true)'

# if configured, the ldap integration schould be disabled,
# as the ldap sync may interfer with the changes the script will apply to user objects
zammad run rails r 'p Setting.get("ldap_integration")'
true
zammad run rails r 'Setting.set("ldap_integration", false)'
zammad run rails r 'p Setting.get("ldap_integration")'
false
```

disable all mail channels etc. ...

#### run

**perform import**

:exclamation: we recommend to run the import against a clone of your productive instance first ; use at your own risk :exclamation:

run:
```
./jira2zammad.py -c jira2zammad.yml -c jira2zammad-secrets.yml -l INFO 2>&1 | tee /var/tmp/jira2zammad.log
```
or if you prefer less output:
```
./jira2zammad.py -c jira2zammad.yml -c jira2zammad-secrets.yml 2>&1 | tee /var/tmp/jira2zammad.log
```

... this can last a long time!

... inspect the log file /var/tmp/jira2zammad.log

#### post import tasks

```
# make changes visible
zammad run rails r 'Setting.set("import_mode", false)'

# rebuild index after import
zammad run rake zammad:searchindex:rebuild[worker]

# enable ldap integration (if applicable)
zammad run rails r 'Setting.set("ldap_integration", true)'
zammad run rails r 'p Setting.get("ldap_integration")'
true
```

enable mail channels etc. ...

**all done - enjoy!**

## links

 * zammad:
   * https://docs.zammad.org/en/latest/api/ticket.html
   * https://zammad-py.readthedocs.io/en/latest/readme.html
 * jira:
   * https://developer.atlassian.com/server/jira/platform/rest/v10004/intro/#gettingstarted
   * https://jira.readthedocs.io/index.html
 * jira issue links:
   * https://developer.atlassian.com/cloud/jira/platform/issue-linking-model/
   + https://www.atlassian.com/blog/developer/jira-issue-linking-model

