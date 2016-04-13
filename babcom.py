#!/usr/bin/env python2
# encoding: utf-8

"""Implementation of Freenet Commmunication Primitives"""


import sys
import argparse # commandline arguments
import cmd # interactive shell
import fcp
import random


slowtests = False


# first, parse commandline arguments
def parse_args():
    """Parse commandline arguments."""
    parser = argparse.ArgumentParser(description="Implementation of Freenet Communication Primitives")
    parser.add_argument('-u', '--user', default=None, help="Identity to use (default: create new)")
    parser.add_argument('--test', default=False, action="store_true", help="Run the tests")
    parser.add_argument('--slowtests', default=False, action="store_true", help="Run the tests")
    args = parser.parse_args()
    return args


# then add interactive usage, since this will be a communication tool
class Babcom(cmd.Cmd):
    prompt = "> "
    
    def do_hello(self, *args):
        """Says Hello. Usage: hello [<name>]"""
        name = args[0] if args else 'World'
        print "Hello {}".format(name)

    def do_quit(self, *args):
        "Leaves the program"
        raise SystemExit

    def do_EOF(self, *args):
        "Leaves the program. Commonly called via CTRL-D"
        raise SystemExit


class ProtocolError(Exception):
    """
    Did not get the expected reply.
    """
    

def _parse_name(wot_identifier):
    """
    Parse identifier of the forms: nick
                                   nick@key
                                   @key
    :Return: nick, key. If a part is not given return an empty string for it.
    
    >>> _parse_name("BabcomTest@123")
    ('BabcomTest', '123')
    """
    split = wot_identifier.split('@', 1)
    nickname_prefix = split[0]
    key_prefix = (split[1] if split[1:] else '')
    return nickname_prefix, key_prefix


def wotmessage(messagetype, **params):
    """Send a message to the Web of Trust plugin

    >>> name = wotmessage("RandomName")["Replies.Name"]
    """
    params["Message"] = messagetype
    with fcp.FCPNode() as n:
        resp = n.fcpPluginMessage(plugin_name="plugins.WebOfTrust.WebOfTrust",
                                  plugin_params=params)[0]
    return resp
    
        

def createidentity(name="BabcomTest"):
    """Create a new Web of Trust identity.

    >>> # createidentity("BabcomTest")
    
    returns {'Replies.Message': 'IdentityCreated', 'Success': 'true', 'Replies.RequestURI': 'USK@...,AQACAAE/WebOfTrust/0', 'Replies.InsertURI': 'USK@...,AQECAAE/WebOfTrust/0', 'header': 'FCPPluginReply', 'PluginName': 'plugins.WebOfTrust.WebOfTrust', 'Replies.ID': '...', 'Identifier': 'id...'}
    """
    if not name:
        name = wotmessage("RandomName")["Name"]
    resp = wotmessage("CreateIdentity", Nickname=name, Context="babcom", # context cannot be empty
                      PublishTrustList="true", # must use string "true"
                      PublishIntroductionPuzzles="true")
    if resp['header'] != 'FCPPluginReply' or resp.get('Replies.Message', "") != 'IdentityCreated':
        raise ProtocolError(resp)
    return name


def parseownidentitiesresponse(response):
    """Parse the response to Get OwnIdentities from the WoT plugin.

    :returns: [(name, {InsertURI: ..., ...}), ...]

    >>> parseownidentitiesresponse({'Replies.Nickname0': 'FAKE', 'Replies.RequestURI0': 'USK@...', 'Replies.InsertURI0': 'USK@...', 'Replies.Identity0': 'fVzf7fg0Va7vNTZZQNKMCDGo6-FSxzF3PhthcXKRRvA', 'Replies.Message': 'OwnIdentities', 'Success': 'true', 'header': 'FCPPluginReply', 'Replies.Properties0.Property0.Name': 'fake', 'Replies.Properties0.Property0.Value': 'true'})
    [('FAKE', {'Contexts': [], 'RequestURI': 'USK@...', 'id_num': '0', 'InsertURI': 'USK@...', 'Properties': {'fake': 'true'}, 'Identity': 'fVzf7fg0Va7vNTZZQNKMCDGo6-FSxzF3PhthcXKRRvA'})]
    """
    field = "Replies.Nickname"
    identities = []
    for i in response:
        if i.startswith(field):
            # format: Replies.Nickname<id_num>
            id_num = i[len(field):]
            nickname = response[i]
            pubkey_hash = response['Replies.Identity{}'.format(id_num)]
            request = response['Replies.RequestURI{}'.format(id_num)]
            insert = response['Replies.InsertURI{}'.format(id_num)]
            contexts = [response[j] for j in response if j.startswith("Replies.Contexts{}.Context".format(id_num))]
            property_keys_keys = [j for j in sorted(response.keys())
                                  if (j.startswith("Replies.Properties{}.Property".format(id_num))
                                      and j.endswith(".Name"))]
            property_value_keys = [j for j in sorted(response.keys())
                                   if (j.startswith("Replies.Properties{}.Property".format(id_num))
                                       and j.endswith(".Value"))]
            properties = dict((response[j], response[k]) for j,k in zip(property_keys_keys, property_value_keys))
            identities.append((nickname, {"id_num": id_num, "Identity":
                                          pubkey_hash, "RequestURI": request, "InsertURI": insert,
                                          "Contexts": contexts, "Properties": properties}))
    return identities


def _requestallownidentities():
    """Get all own identities.

    >>> resp = _requestallownidentities()
    >>> name, info = _matchingidentities("BabcomTest", resp)[0]
    """
    with fcp.FCPNode() as n:
        # n.verbosity = 5
        resp = n.fcpPluginMessage(plugin_name="plugins.WebOfTrust.WebOfTrust",
                                  plugin_params={"Message": "GetOwnIdentities"})[0]
    if resp['header'] != 'FCPPluginReply' or resp.get('Replies.Message', '') != 'OwnIdentities':
        return None
    return resp

    
def _matchingidentities(prefix, response):
    """Find matching identities in a Web of Trust Plugin response.

    >>> _matchingidentities("BabcomTest", {})
    []
    """
    identities = parseownidentitiesresponse(response)
    nickname_prefix, key_prefix = _parse_name(prefix)
    return [(name, info) for name,info in identities
            if (info["Identity"].startswith(key_prefix) and
                name.startswith(nickname_prefix))]


def getownidentities(user):
    """Get all own identities which match user."""
    resp = _requestallownidentities()
    return _matchingidentities(user, resp)

    
def myidentity(user=None):
    """Get an identity from the Web of Trust plugin.

    :param user: Name of the Identity, optionally with additional
                 prefix of the key to disambiguate it.

    If there are multiple IDs matching the name, the user has to
    disambiguate them by selecting one or by adding parts of the
    identity key to the name.

    :returns: [(name, info), ...]
    
    >>> matches = myidentity("BabcomTest")
    >>> matches[0][0]
    'BabcomTest'

    """
    if user is None:
        user = createidentity()
    matches = getownidentities(user)
    if not matches:
        createidentity(user)
        matches = getownidentities(user)
    
    return matches


def addcontext(identity, context):
    """Add a context to an identity to show others that it supports a certain service.

    >>> matches = myidentity("BabcomTest")
    >>> name, info = matches[0]
    >>> identity = info["Identity"]
    >>> addcontext(identity, "testadd")
    >>> matches = myidentity(name)
    >>> info = matches[0][1]
    >>> "testadd" in info["Contexts"]
    True
    """
    with fcp.FCPNode() as n:
        resp = n.fcpPluginMessage(plugin_name="plugins.WebOfTrust.WebOfTrust",
                                  plugin_params={"Message": "AddContext",
                                                 "Identity": identity,
                                                 "Context": context})[0]
    if resp['header'] != 'FCPPluginReply' or resp.get('Replies.Message', '') != 'ContextAdded':
        raise ProtocolError(resp)
    

def removecontext(identity, context):
    """Add a context to an identity to show others that it supports a certain service.

    >>> matches = myidentity("BabcomTest")
    >>> name, info = matches[0]
    >>> identity = info["Identity"]
    >>> addcontext(identity, "testremove")
    >>> removecontext(identity, "testremove")
    >>> removecontext(identity, "testadd")
    """
    with fcp.FCPNode() as n:
        resp = n.fcpPluginMessage(plugin_name="plugins.WebOfTrust.WebOfTrust",
                                  plugin_params={"Message": "RemoveContext",
                                                 "Identity": identity,
                                                 "Context": context})[0]
    if resp['header'] != 'FCPPluginReply' or resp.get('Replies.Message', '') != 'ContextRemoved':
        raise ProtocolError(resp)
    

def ssktousk(ssk, foldername):
    """Convert an SSK to a USK.

    >>> ssktousk("SSK@pAOgyTDft8bipMTWwoHk1hJ1lhWDvHP3SILOtD1e444,Wpx6ypjoFrsy6sC9k6BVqw-qVu8fgyXmxikGM4Fygzw,AQACAAE/", "folder")
    'USK@pAOgyTDft8bipMTWwoHk1hJ1lhWDvHP3SILOtD1e444,Wpx6ypjoFrsy6sC9k6BVqw-qVu8fgyXmxikGM4Fygzw,AQACAAE/folder/0'
    """
    return "".join(("U", ssk[1:].split("/")[0],
                    "/", foldername, "/0"))

    
def fastput(node, private, data):
    """Upload a small amount of data as fast as possible.

    >>> with fcp.FCPNode() as n:
    ...    pub, priv = n.genkey(name="hello.txt")
    ...    if slowtests:
    ...        pubtoo = fastput(n, priv, "Hello Friend!")
    >>> with fcp.FCPNode() as n:
    ...    pub, priv = n.genkey()
    ...    insertusk = ssktousk(priv, "folder")
    ...    if slowtests:
    ...        pub = fastput(n, insertusk, "Hello USK")
    ...    else: pub = "something,AQACAAE/folder/0"
    ...    pub.split(",")[-1]
    'AQACAAE/folder/0'
    """
    return node.put(uri=private, data="Hello Friend!",
                    mimetype="application/octet-stream",
                    realtime=True, priority=1)


def fastget(node, public):
    """Download a small amount of data as fast as possible.

    >>> with fcp.FCPNode() as n:
    ...    pub, priv = n.genkey(name="hello.txt")
    ...    data = "Hello Friend!"
    ...    if slowtests:
    ...        pubkey = fastput(n, priv, data)
    ...        fastget(n, pub)[1]
    ...    else: data
    'Hello Friend!'
    """
    return node.get(public,
                    realtime=True, priority=1)


def getinsertkey(identity):
    """Get the insert key of the given identity.

    >>> matches = myidentity("BabcomTest")
    >>> name, info = matches[0]
    >>> identity = info["Identity"]
    >>> insertkey = getinsertkey(identity)
    >>> insertkey.split("/")[0].split(",")[-1]
    'AQECAAE'
    """
    resp = _requestallownidentities()
    identities = parseownidentitiesresponse(resp)
    insertkeys = [info["InsertURI"]
                  for name,info in identities
                  if info["Identity"] == identity]
    if insertkeys[1:]:
        raise ProtocolError(
            "More than one insert key for the same identity: {}".format(
                insertkeys))
    return insertkeys[0]


def createcaptchas(number=10, seed=None):
    """Create text captchas

    >>> createcaptchas(number=1, seed=42)
    [('KSK@hBQM_njuE_XBMb_? with 10 plus 32 = ?', 'hBQM_njuE_XBMb_42')]
    
    :returns: [(captchatext, solution), ...]
    """
    # prepare the random number generator for reproducible tests.
    random.seed(seed)
    
    def plus(x, y):
        "KSK@{2}? with {0} plus {1} = ?"
        return x + y
        
    def minus(x, y):
        "KSK@{2}? with {0} minus {1} = ?"
        return x - y
        
    def plusequals(x, y):
        "KSK@{2}? with {0} plus ? = {1}"
        return y - x
        
    def minusequals(x, y):
        "KSK@{2}? with {0} minus ? = {1}"
        return x + y
        
    questions = [plus, minus,
                 plusequals,
                 minusequals]

    captchas = []
    
    def fourletters():
        return [random.choice("ABCDEFHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
                for i in range(4)]
    
    secret = "".join(fourletters() + ["_"] +
                     fourletters() + ["_"] +
                     fourletters() + ["_"])
    for i in range(number):
        question = random.choice(questions)
        x = random.randint(1, 49)
        y = random.randint(1, 49)
        captcha = question.__doc__.format(x, y, secret)
        solution = secret + str(question(x, y))
        captchas.append((captcha, solution))

    return captchas


def insertcaptchas(identity):
    """Insert a list of CAPTCHAs.

    >>> matches = myidentity("BabcomTest")
    >>> name, info = matches[0]
    >>> identity = info["Identity"]
    >>> if slowtests:
    ...     usk, solutions = insertcaptchas(identity)
    ...     solutions[0][:4]
    ... else: "KSK@"
    'KSK@'

    :returns: captchasuri, ["KSK@solution", ...]
    """
    insertkey = getinsertkey(identity)
    captchas = createcaptchas()
    captchasdata = "\n".join(captcha for captcha,solution in captchas)
    captchasolutions = [solution for captcha,solution in captchas]
    captchausk = ssktousk(insertkey, "babcomcaptchas")
    with fcp.FCPNode() as n:
        pub = fastput(n, captchausk, captchasdata)
    return pub, ["KSK@" + solution
                 for solution in captchasolutions]
    

def announcecaptchas(identity):
    """Provide a link to the CAPTCHA queue as property of the identity.

    >>> matches = myidentity("BabcomTest")
    >>> name, info = matches[0]
    >>> identity = info["Identity"]
    >>> if slowtests:
    ...     solutions = announcecaptchas(identity)
    ...     matches = myidentity("BabcomTest")
    ...     name, info = matches[0]
    ...     "babcomcaptchas" in info["Properties"]
    ... else: True
    True
    
    :returns: ["KSK@...", ...] # the solutions to watch
    """
    pubusk, solutions = insertcaptchas(identity)
    resp = wotmessage("SetProperty", Identity=identity,
                      Property="babcomcaptchas",
                      Value=pubusk)
    if resp['header'] != 'FCPPluginReply' or resp.get('Replies.Message', "") != 'PropertyAdded':
        raise ProtocolError(resp)

    return solutions


def gettrust(truster, trustee):
    """Set trust to an identity.

    >>> my = myidentity("BabcomTest")[0][1]["Identity"]
    >>> other = myidentity("BabcomTest_other")[0][1]["Identity"]
    >>> gettrust(my, other)
    'Nonexistent'
    """
    resp = wotmessage("GetTrust",
                      Truster=truster, Trustee=trustee)
    if resp['header'] != 'FCPPluginReply' or resp.get('RepliesMessage', "") != 'Trust':
        raise ProtocolError(resp)
    return resp['Replies.Trusts.0.Value']


def settrust(myidentity, otheridentity, trust, comment):
    """Set trust to an identity.

    :param trust: -100..100. 
                  -100 to -2: report as spammer, do not download.
                  -1: do not download.
                  0: download and show.
                  1 to 100: download, show and mark as non-spammer so
                      others download the identity, too.
    """
    resp = wotmessage("SetTrust",
                      Truster=myidentity, Trustee=otheridentity,
                      Value=str(trust), Comment=comment)
    if resp['header'] != 'FCPPluginReply' or resp.get('RepliesMessage', "") != 'TrustSet':
        raise ProtocolError(resp)




def _test():

    """Run the tests

    >>> True
    True
    """
    try:
        import newbase60
        numtostring = newbase60.numtosxg
    except:
        numtostring = str
        
    import doctest
    tests = doctest.testmod()
    if tests.failed:
        return "☹"*tests.failed + " / " + numtostring(tests.attempted)
    return "^_^ (" + numtostring(tests.attempted) + ")"


if __name__ == "__main__":
    args = parse_args()
    slowtests = args.slowtests
    if args.test:
        print _test()
        sys.exit(0)
    prompt = Babcom()
    prompt.cmdloop('Starting babcom, type help for help')
