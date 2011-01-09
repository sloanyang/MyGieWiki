# this:	Config.py
# by:	Poul Staugaard (poul(dot)staugaard(at)gmail...)
# URL:	http://code.google.com/p/giewiki
# ver.:	1.8.0

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
from google.appengine.api import namespace_manager

from giewikidb import UserProfile

HttpMethods = '\
createPage\n\
editTiddler\n\
unlockTiddler\n\
lockTiddler\n\
saveTiddler\n\
deleteTiddler\n\
revertTiddler\n\
deleteVersions\n\
tiddlerHistory\n\
tiddlerVersion\n\
tiddlerDiff\n\
getLoginUrl\n\
pageProperties\n\
userProfile\n\
getUserInfo\n\
addProject\n\
deletePage\n\
getNewAddress\n\
submitComment\n\
getComments\n\
getNotes\n\
getMessages\n\
getTiddler\n\
getTiddlers\n\
fileList\n\
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
updateTemplate\n\
getTemplates'

jsProlog = '\
var giewikiVersion = { title: "giewiki", major: 1, minor: 8, revision: 0, date: new Date("Dec 31, 2010"), extensions: {} };\n\
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
	project: "<project>",\n\
	options: {\n\
		' # the rest is built dynamically

def isNameAnOption(name):
	return name.startswith('txt') or name.startswith('chk')

def jsEncodeStr(s):
	return '"' + unicode(s).replace(u'"',u'\\"').replace(u'\n',u'\\n').replace(u'\r',u'') + u'"'

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
	self.configOptions = list()
	isLoggedIn = user != None
	self.response.headers['Content-Type'] = 'application/x-javascript'
	self.response.headers['Cache-Control'] = 'no-cache'
	self.response.out.write(jsProlog.replace("<project>",self.getSubdomain()))
	if isLoggedIn:
		upr = UserProfile.all().filter('user',user).get() # my profile
		if upr == None:
			upr = UserProfile(txtUserName = user.nickname()) # my null profile
		else:
			upr.txtUserName == user.nickname()
	else:
		upr = UserProfile(txtUserName='IP \t' + self.request.remote_addr) # anon null profile
		
	optlist = [ 'isLoggedIn: ' + ('true' if isLoggedIn else 'false') ]
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
