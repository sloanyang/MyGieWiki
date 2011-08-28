# this:	Config.py
# by:	Poul Staugaard (poul(dot)staugaard(at)gmail...)
# URL:	http://code.google.com/p/giewiki
# ver.:	1.14.0

import cgi
import codecs
import datetime
import logging
import os
import re
import urllib
import urlparse

from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.api import namespace_manager

from giewikidb import UserProfile,Page,AccessToPage,noSuchTiddlers

HttpMethods = '\
createPage\n\
editTiddler\n\
unlockTiddler\n\
lockTiddler\n\
saveTiddler\n\
addTags\n\
changeTags\n\
deleteFile\n\
deleteTiddler\n\
revertTiddler\n\
deleteVersions\n\
tiddlerHistory\n\
tiddlerVersion\n\
tiddlerDiff\n\
getLoginUrl\n\
pageProperties\n\
clipboard\n\
userProfile\n\
getUserInfo\n\
addProject\n\
deletePage\n\
getNewAddress\n\
submitComment\n\
deleteComment\n\
alterComment\n\
getComments\n\
getNotes\n\
getMessages\n\
getTiddler\n\
getTiddlers\n\
listTiddlersTagged\n\
fileList\n\
replaceExistingFile\n\
recycleBin\n\
getRecentChanges\n\
getRecentComments\n\
siteMap\n\
getGroups\n\
createGroup\n\
getGroupMembers\n\
addGroupMember\n\
removeGroupMember\n\
evaluate\n\
tiddlersFromUrl\n\
openLibrary\n\
listScripts\n\
updateTemplate\n\
getTemplates'

jsProlog = '\
// This file is auto-generated\n\
var giewikiVersion = { title: "giewiki", major: 1, minor: 14, revision: 0, date: new Date("July 23, 2011"), extensions: {} };\n\
http = {\n\
  _methods: [],\n\
  _addMethod: function(m) { this[m] = new Function("a","return HttpGet(a,\'" + m + "\')"); }\n\
}\n\
\n\
http._init = function(ms) { for (var i=0; i < ms.length; i++) http._addMethod(ms[i]); }\n\
var config = {\n\
	animDuration: 400,\n\
	cascadeFast: 20,\n\
	cascadeSlow: 60,\n\
	cascadeDepth: 5,\n\
	locale: "en",\n\
	admin: <isAdmin>,\n\
	loginName: <loginName>,\n\
	owner: <pageOwner>,\n\
	access: "<access>",\n\
	anonAccess: "<anonAccess>",\n\
	authAccess: "<authAccess>",\n\
	groupAccess: "<groupAccess>",\n\
	groups: <userGroups>,\n\
	project: "<project>",\n\
	sitetitle: <sitetitle>,\n\
	subtitle: <subtitle>,\n\
	locked: <isLocked>,\n\
	tiddlerTags: <tiddlerTags>,\n\
	viewButton: <viewButton>,\n\
	viewPrior: <viewPrior>,\n\
	foldIndex: <foldIndex>,\n\
	serverType: "<servertype>",\n\
	clientip: "<clientIP>",\n\
	timeStamp: "<timestamp>",\n\
	warnings: <allWarnings>,\n\
	pages: [ <siblingPages> ],\n\
	deprecatedCount: <deprecatedCount>,\n\
	noSuchTiddlers: <noSuchTiddlers>,\n\
	options: {\n\
		' # the rest is built dynamically

def isNameAnOption(name):
	return name.startswith('txt') or name.startswith('chk')

def AttrValueOrBlank(o,a):
	return unicode(getattr(o,a)) if o != None and hasattr(o,a) and getattr(o,a) != None else ''

def jsEncodeStr(s):
	return 'null' if s is None else u'"' + unicode(s).replace(u'"',u'\\"').replace(u'\n',u'\\n').replace(u'\r',u'') + u'"'

def jsEncodeBool(b):
	return 'true' if b else 'false'

def IsIPaddress(v):
	if len(v) < 4:
		return False
	lix = len(v) - 1
	if v[lix].find(':') > 0:
		v[lix] = v[lix].split(':')[0]
	for a in range(len(v)-4,len(v)):
		try:
			n = int(v[a])
			if n < 0 or n > 255:
				return False
		except Exception:
			return False
	return True
	
class ConfigJs(webapp.RequestHandler):
  def getSubdomain(self):
	hostc = self.request.host.split('.')
	if len(hostc) > 3: # e.g. subdomain.giewiki.appspot.com
		if IsIPaddress(hostc): # [sd.]n.n.n.n[:port]
			pos = len(hostc) - 5
		else:
			pos = len(hostc) - 4
	elif len(hostc) > 1 and hostc[len(hostc) - 1].startswith('localhost'): # e.g. sd.localhost:port
		pos = len(hostc) - 2
	# elif... support for app.org.tld domains -- TODO
	else:
		return ""

	if pos >= 0 and hostc[pos] != 'latest': # App engine uses this for alternate versions
		sd = hostc[pos]
		namespace_manager.set_namespace(sd)
		return sd
	else:
		return ""

  def AppendConfigOption(self,list,fn,fv):
	self.configOptions.append(fn)
	list.append(fn + ': ' + fv)

  def get(self):
	'Dynamically construct file "/config.js"'
	user = users.get_current_user()
	self.getSubdomain()
	page = memcache.get(self.request.remote_addr)
	warnings = memcache.get("W:" + self.request.remote_addr)
	userGroups = ''
	pages = []
	noSuchTdlrs = None
	if page is None or page.is_saved() == False:
		logging.error("page not found in memcache" if page is None else "Page is new")
		yourAccess =  'view' if page is None else 'admin' # admin when db is blank
		anonAccess = 'view' #?
		authAccess = 'view' #?
		groupAccess = 'view'#?
		owner = ''
		locked = False
		deprecatedCount = 0
		siteTitle = ''
		subTitle = ''
		viewButton = 'false'
		viewPrior = 'false'
		foldIndex = 'false'
	else:
		yourAccess = AccessToPage(page,user)
		anonAccess = page.access[page.anonAccess]
		authAccess = page.access[page.authAccess]
		groupAccess = page.access[page.groupAccess]
		if (not page.ownername is None) and (user is None or user.nickname() != page.owner.nickname()):
			owner = page.ownername
		else:
			owner = page.owner.nickname()
		if page.groups != None:
			userGroups = page.groups
		viewButton = 'true' if hasattr(page,'viewbutton') and page.viewbutton else 'false'
		viewPrior = 'true' if hasattr(page,'viewprior') and page.viewprior else 'false'
		foldIndex = 'true' if hasattr(page,'foldIndex') and page.foldIndex else 'false'
		siteTitle = page.title
		subTitle = page.subtitle
		locked = page.locked
		deprecatedCount = page.deprecatedCount
		if hasattr(page,noSuchTiddlers):
			noSuchTdlrs = page.noSuchTiddlers

		papalen = page.path.rfind('/')
		if papalen == -1:
			paw = ""
		else:
			paw = page.path[0:papalen + 1]
		for p in Page.all():
			if p.path.startswith(paw): # list sibling pages
				pages.append(''.join(['{ p:', jsEncodeStr(p.path), ',t:', jsEncodeStr(p.title), ',s:', jsEncodeStr(p.subtitle),'}']))
		logging.info("Config for " + page.path + ": " + page.title)

	self.configOptions = list()
	isLoggedIn = user != None
	self.response.headers['Content-Type'] = 'application/x-javascript'
	self.response.headers['Cache-Control'] = 'no-cache'
	loginName = 'null' if user is None else jsEncodeStr(user.nickname())
	self.response.out.write( jsProlog\
		.replace('<project>',self.getSubdomain(),1)\
		.replace('<sitetitle>',jsEncodeStr(siteTitle),1)\
		.replace('<subtitle>',jsEncodeStr(subTitle),1)\
		.replace('<isLocked>', jsEncodeBool(locked),1)\
		.replace('<tiddlerTags>',jsEncodeStr(AttrValueOrBlank(page,'tiddlertags')),1)\
		.replace('<viewButton>',viewButton,1)\
		.replace('<viewPrior>',viewPrior,1)\
		.replace('<foldIndex>',foldIndex,1)\
		.replace('<servertype>',os.environ['SERVER_SOFTWARE'],1)\
		.replace('<isAdmin>','true' if users.is_current_user_admin() else 'false',1)\
		.replace('<loginName>',loginName,1)\
		.replace('<pageOwner>',jsEncodeStr(owner),1)\
		.replace('<access>',yourAccess,1)\
		.replace('<anonAccess>',anonAccess,1)\
		.replace('<authAccess>',authAccess,1)\
		.replace('<groupAccess>',groupAccess,1)\
		.replace('<userGroups>',jsEncodeStr(userGroups),1)\
		.replace('<clientIP>',self.request.remote_addr,1)\
		.replace('<deprecatedCount>', str(deprecatedCount),1)\
		.replace('<allWarnings>',jsEncodeStr(warnings),1)\
		.replace('<noSuchTiddlers>',jsEncodeStr(noSuchTdlrs),1)\
		.replace('<siblingPages>', ',\n'.join(pages),1)\
		.replace('<timestamp>', unicode(datetime.datetime.now()),1)) # time.strftime("%Y-%m-%d-%H:%M:%S"),1))
	if isLoggedIn:
		upr = UserProfile.all().filter('user',user).get() # my profile
		if upr == None:
			upr = UserProfile(txtUserName = user.nickname()) # my null profile
		else:
			upr.txtUserName == user.nickname()
	else:
		upr = UserProfile(txtUserName='IP \t' + self.request.remote_addr) # anon null profile
		
	optlist = []
	for (fn,ft) in upr._properties.iteritems():
		fv = getattr(upr,fn)
		if fv != None:
			if type(getattr(UserProfile,fn)) == db.BooleanProperty:
				fv = 'true' if fv else 'false'
			else:
				fv = jsEncodeStr(fv)
			if isNameAnOption(fn):
				self.AppendConfigOption(optlist,fn, fv)
	for (fn,ft) in upr._dynamic_properties.iteritems():
		fv = getattr(upr,fn)
		if fv != None:
			if fn.startswith('chk'):
				fv = 'true' if fv else 'false'
			else:
				fv = jsEncodeStr(fv)
			if isNameAnOption(fn):
				self.AppendConfigOption(optlist,fn, fv)

	if isLoggedIn and not 'txtUserName' in self.configOptions:
		self.AppendConfigOption(optlist,'txtUserName',jsEncodeStr(user.nickname()))

	self.response.out.write(',\n\t\t'.join(optlist))
	self.response.out.write('\n\t}\n};\nhttp._init(["')
	self.response.out.write('","'.join(HttpMethods.split('\n')))
	self.response.out.write('"]);')

############################################################################

application = webapp.WSGIApplication( [('/.*', ConfigJs)], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
