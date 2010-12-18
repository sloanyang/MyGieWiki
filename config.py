# /****************************************************
# this:	Config.py
# by:	Poul Staugaard (poul(dot)staugaard(at)gmail...)
# URL:	http://code.google.com/p/giewiki
# ver.:	1.6.4

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

from giewikidb import UserProfile

jsProlog = '\
var giewikiVersion = { title: "giewiki", major: 1, minor: 6, revision: 4, date: new Date("Dec 16, 2010"), extensions: {} };\n\
var config = {\n\
	animDuration: 400,\n\
	cascadeFast: 20,\n\
	cascadeSlow: 60,\n\
	cascadeDepth: 5,\n\
	locale: "en",\n\
	options: {\n\
		' # the rest is built dynamically

def isNameAnOption(name):
	return name.startswith('txt') or name.startswith('chk')

def jsEncodeStr(s):
	return '"' + unicode(s).replace(u'"',u'\\"').replace(u'\n',u'\\n').replace(u'\r',u'') + u'"'
	
class ConfigJs(webapp.RequestHandler):
  def AppendConfigOption(self,list,fn,fv):
	self.configOptions.append(fn)
	list.append(fn + ': ' + fv)
  
  def get(self):
	'Dynamically construct file "/config.js"'
	user = users.get_current_user()
	self.configOptions = list()
	isLoggedIn = user != None
	self.response.headers['Content-Type'] = 'application/x-javascript'
	self.response.headers['Cache-Control'] = 'no-cache'
	self.response.out.write(jsProlog)
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
	self.response.out.write('\n\t}\n};')
############################################################################

application = webapp.WSGIApplication( [('/.*', ConfigJs)], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
