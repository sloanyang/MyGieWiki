# this:	iewiki.py
# by:	Poul Staugaard
# URL:	http://code.google.com/p/giewiki
# ver.:	1.3.0

import cgi
import uuid
import urllib
import xml.dom.minidom

from datetime import *
from new import instance, classobj
from os import path

from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.api import urlfetch 

from Tiddler import *
from Plugins import *
from giewikilib import *

class MainPage(webapp.RequestHandler):
  "Serves wiki pages and updates"
  trace = list()
  merge = False
  subdomain = None

  def getSubdomain(self):
	hostc = self.request.host.split('.')
	if len(hostc) > 3: # e.g. subdomain.giewiki.appspot.com
		pos = len(hostc) - 4
	elif len(hostc) > 1 and hostc[len(hostc) - 1].startswith('localhost'): # e.g. sd.localhost:port
		pos = len(hostc) - 2
	# elif... support for app.org.tld domains -- TODO
	else:
		self.merge = False
		self.subdomain = None
		return

	self.subdomain = hostc[pos]
	self.merge = False
	if pos > 0:
		if hostc[0] == 'merge':
			self.merge = True

  def initXmlResponse(self):
	self.response.headers['Content-Type'] = 'text/xml'
	self.response.headers['Cache-Control'] = 'no-cache'
	return XmlDocument()

  def sendXmlResponse(self,xd):
	self.initXmlResponse()
	self.response.out.write(xd.toxml())

  def initHist(self,title):
	versions = '|When|Who|V#|Title|\n'
	if self.request.get("shadow") == '1':
		versions += '|>|Default content|0|<<revision "' + title + '" 0>>|\n'
	return versions;
  
  def SaveNewTiddler(self,page,name,value):
	p = Tiddler()
	p.page = page
	p.sub = self.subdomain 
	p.author = users.get_current_user()
	p.author_ip = self.request.remote_addr
	p.version = 1
	p.comments = 0
	p.current = True
	p.title = name
	p.text = value
	p.tags = ""
	p.id = str(uuid.uuid4())
	p.save()
	return p

  def lock(self,t,usr):
	try:
		minutes = int(self.request.get("duration"))
	except:
		minutes = 0
		
	el = EditLock( id = t.id, user = usr, user_ip = self.request.remote_addr, duration = minutes)
	ek = el.put()
	until = el.time + timedelta(0,60*eval(str(el.duration)))
	return {"Success": True, "now": el.time, "until": until, "key": str(ek), "title": t.title, "text": t.text, "tags": t.tags }
  
  def editTiddler(self):
	"http version tiddlerId"
	page = Page.all().filter("path",self.request.path).get()
	if page == None:
		error = "Page does not exist: " + self.request.path
	else:
		error = page.UpdateViolation()
	if error == None:
		tid = self.request.get("id")
		if tid.startswith('include-'):
			return self.fail("Included from " + tid[8:])
		t = Tiddler.all().filter("id",tid).filter("current",True).get()
		if t == None:
			error = "Tiddler doesn't exist"
		else:
			usr = users.get_current_user()
			el = EditLock().all().filter("id",t.id).get() # get existing lock, if any
			if el == None: # tiddler is not locked
				return self.reply(self.lock(t,usr))
			until = el.time + timedelta(0,60*eval(str(el.duration)))
			if (usr == el.user if usr != None else self.request.remote_addr == el.user_ip):
				# possibly we should extend the lock duration
				return self.fail("already locked by you", { "key": str(el.key()) })
			elif datetime.datetime.utcnow() < until:
				error = "already locked by " + userNameOrAddress(el.user, el.user_ip) + \
						" until " + str(until) + "( another " + str(until -  datetime.datetime.utcnow()) + ")"
			else:
				el.delete()
				reply = self.lock(t,usr)
				reply['until'] = until
				return self.warn( "Lock held by " + userNameOrAddress(el.user, el.user_ip) + " broken", reply)
	self.fail(error)

  def unlock(self,key):
	lock = EditLock.get(key)
	if lock != None:
		lock.delete()
		return True
	else:
		return self.fail("Lock was not held")
	
  def unlockTiddler(self):
	if self.unlock(self.request.get("key")):
		self.reply({})

  def lockTiddler(self):
	t = Tiddler.all().filter('id',self.request.get("tiddlerId")).filter('current',True).get()
	if t != None:
		t.locked = self.request.get("lock") == 'true'
		t.put()
		self.reply({"Success": True})
	else:
		self.fail('no such tiddler')

  def saveTiddler(self):
	"http tiddlerName text tags version tiddlerId versions"
	tlr = Tiddler()
	tlr.page = self.request.path
	tlr.id = self.request.get("tiddlerId")
	page = Page.all().filter("path",tlr.page).get()
	if page == None:
		error = "Page does not exist: " + tlr.page
	else:
		error = page.UpdateViolation()

	if tlr.id != '':
		if tlr.id.startswith('include-'):
			# break the link and create a new tiddler
			nt = self.SaveNewTiddler(tlr.page, self.request.get("tiddlerName"),self.request.get("text"))
			return self.reply({"Success": True, "id": nt.id})
		key = self.request.get("key")
		if key == "":
			t = Tiddler.all().filter("id", tlr.id).get()
			if t == None:
				error = "Tiddler doesnt' exist"
			else:
				el = EditLock().all().filter("id",t.id).get() # locked by someone else?
				if el != None:
					error = "Locked by " + userNameOrAddress(el.user,el.user_ip)
		elif self.unlock(key) == False:
			return
			
	if error!= None:
		return self.fail(error)
		
	tlr.public = page.anonAccess > page.NoAccess
	tlr.title = self.request.get("tiddlerName")
	tlr.text = self.request.get("text")
	tlr.tags = self.request.get("tags")
	tlr.version = eval(self.request.get("version"))
	tlr.comments = 0
	if (tlr.id == ""):
		tlr.id = str(uuid.uuid4())
	if users.get_current_user():
		tlr.author = users.get_current_user()
	tlr.author_ip = self.request.remote_addr # ToDo: Get user's sig in stead

	tls = Tiddler.all().filter('id', tlr.id).filter('version >=',tlr.version - 1)
	
	versions = self.request.get("versions")
	getPrior = False
	if versions == '':
		getPrior = True
		versions = self.initHist(tlr.title);
	for atl in tls:
		if getPrior or atl.version == tlr.version:
			if atl.author != None:
				by = atl.author.nickname()
			else:
				by = self.request.remote_addr
			versions = versions + "|" + atl.modified.strftime("%Y-%m-%d %H:%M") + "|" + by + "|" + str(atl.version) + '|<<revision "' + atl.title + '" ' + str(atl.version) + '>>|\n'
		if atl.version >= tlr.version:
			tlr.version = atl.version + 1
			tlr.comments = atl.comments;
		if atl.current:
			if atl.sub == self.subdomain:
				atl.current = False
				tlr.comments = atl.comments
				tlr.sub = atl.sub
				atl.put()
			elif atl.sub == None: # automatically lock public version
				atl.locked = True
				atl.put()
				
	tlr.current = True
	tlr.sub = self.subdomain
	if "includes" in tlr.tags.split():
		tlf = list()
		tls = tlr.text.split("\n")
		for tlx in tls:
			link = tlx.strip(' \r\n\t')
			if link == "":
				continue
				
			if not (link.startswith("[[") and link.endswith("]]")):
				link = '[[' + link + "|" + link + ']]'

			tli = link.lstrip('[').rstrip(']').split("|").pop()  # test the URL part
					
			parts = tli.split("#")
			if len(parts) == 2:
				tlxs = Tiddler.all().filter("page", parts[0]).filter("title", parts[1]).filter("current",True).get()
				if tlxs != None:
					incl = Include.Unique(tlr.page,tlxs.id)
					if "current" in tlr.tags.split():
						incl.version = tlxs.version
					else:
						incl.version = None
					incl.put()
					tlf.append(link)
				else:
					tlf.append(link + " ''not found''")

		tlr.text = '\n'.join(tlf)
	
	tlr.put()
	if page != None:
		page.Update(tlr)

	tags = tlr.tags.split()
	isShared = True if ("shadowTiddler" in tags or "sharedTiddler" in tags) else False
	st = ShadowTiddler.all().filter('id',tlr.id).get()
	if st != None:
		if isShared:
			st.tiddler = tlr
		else:
			st.delete()
		
	if isShared and st == None:
		s = ShadowTiddler(tiddler = tlr, path = tlr.page, id = tlr.id)
		s.put()
	
	xd = self.initXmlResponse()
	esr = xd.add(xd,'SaveResp')
	xd.appendChild(esr)
	we = xd.createElement('when')
	we.setAttribute('type','datetime')
	we.appendChild(xd.createTextNode(tlr.modified.strftime("%Y%m%d%H%M%S")))
	ide = xd.createElement('id')
	ide.appendChild(xd.createTextNode(str(tlr.id)))

	if tlr.author != None:
		by = tlr.author.nickname()
	else:
		by = self.request.remote_addr;
	versions = versions + "|" + tlr.modified.strftime("%Y-%m-%d %H:%M") + "|" + by + "|" + str(tlr.version) + '|<<revision "' + tlr.title + '" ' + str(tlr.version) + '>>|\n'
	ve = xd.createElement('versions')
	ve.appendChild(xd.createTextNode(versions))
	esr.appendChild(we)
	esr.appendChild(ide)
	esr.appendChild(ve)
	self.response.out.write(xd.toxml())
	
  def tiddlerHistory(self):
	"http tiddlerId"
	xd = self.initXmlResponse()
	tls = Tiddler.all().filter("id", self.request.get("tiddlerId"))
	eHist = xd.add(xd,'Hist')
	eVersions = xd.createElement('versions')
	eHist.appendChild(eVersions)
	text = ""
	for tlr in tls:
		if text == "":
			text = self.initHist(tlr.title);
		text += "|" + tlr.modified.strftime("%Y-%m-%d %H:%M") + "|" + getAuthor(tlr) + "|" + str(tlr.version) + '|<<revision "' + htmlEncode(tlr.title) + '" ' + str(tlr.version) + '>>|\n'
	
	eVersions.appendChild(xd.createTextNode(text))
	self.response.out.write(xd.toxml())

  def tiddlerVersion(self):
	self.initXmlResponse()
	tls = Tiddler.all().filter('id', self.request.get("tiddlerId")).filter('version',int(self.request.get("version")))
	xd = xml.dom.minidom.Document()
	tv = xd.createElement('TiddlerVersion')
	xd.appendChild(tv)
	found = 0
	for tlr in tls:
		te = xd.createElement('text')
		tv.appendChild(te)
		te.appendChild(xd.createTextNode(tlr.text))
		
		te = xd.createElement('title')
		tv.appendChild(te)
		te.appendChild(xd.createTextNode(tlr.title))

		te = xd.createElement('version')
		tv.appendChild(te)
		te.appendChild(xd.createTextNode(str(tlr.version)))
		te.setAttribute('type','int')

		te = xd.createElement('modified')
		tv.appendChild(te)
		te.appendChild(xd.createTextNode(tlr.modified.strftime("%Y%m%d%H%M%S")))
		te.setAttribute('type','datetime')

		te = xd.createElement('modifier')
		tv.appendChild(te)
		te.appendChild(xd.createTextNode(getAuthor(tlr)))

		te = xd.createElement('tags')
		tv.appendChild(te)
		xmlArrayOfStrings(xd,te,tlr.tags,'tag')
		## te.appendChild(xd.createTextNode(tlr.tags))

		found += 1
	if found != 1:
		err = xd.createElement('error')
		tv.appendChild(err)
		err.appendChild(xd.createTextNode(self.request.get("tiddlerId") + ': ' + self.request.get("version") + ' found ' + str(found)))
	self.response.out.write(xd.toxml())

  def deleteTiddler(self):
	self.initXmlResponse()
	tid = self.request.get("tiddlerId")
	if tid.startswith('include-'):
		page = self.CurrentPage()
		urlparts = tid[8:].split('#')
		url = urlparts[0] + '#'
		part = urlparts[1]
		siLines = page.systemInclude.split('\n')
		for ali in siLines:
			if ali.startswith(url):
				sl = ali[len(url):].split('||')
				sl.remove(part)
				url = url + '||'.join(sl)
				siLines.remove(ali)
				siLines.append(url)
				page.systemInclude = '\n'.join(siLines)
				page.put()
				return self.warn("tiddler excluded")
				
	tls = Tiddler.all().filter('id', tid)
	any = False
	for tlr in tls:
		tlr.delete()
		any = True
	for st in ShadowTiddler.all().filter('id',tid):
		st.delete()
		
	xd = xml.dom.minidom.Document()
	tv = xd.createElement('TiddlerDelete')
	xd.appendChild(tv)
	self.response.out.write(xd.toxml())
	
  def add(self):
	self.reply({"Success": True, "result": int(self.request.get("a")) + int(self.request.get("b"))})
	

  def submitComment(self):
	tls = Tiddler.all().filter('id', self.request.get("tiddler")).filter('current',True).get()
	if tls == None:
		return self.reply({"Success": False, "Message": "No such tiddler!"})
	t = self.request.get("type")
	if t == "N":
		comment = Note()
	elif t == "M":
		comment = Message()
		comment.receiver = users.User(self.request.get("receiver"))
	else:
		comment = Comment()
	comment.tiddler = self.request.get("tiddler")
	comment.version = int(self.request.get("version"))
	comment.text = self.request.get("text")
	comment.author = users.get_current_user()
	comment.ref = self.request.get("ref")
	comment.save()
	if t == "C" and comment.ref == "":
		tls.comments = tls.comments + 1
	elif t == "M":
		if tls.messages == None:
			tls.messages = '|'
		tls.messages = tls.messages + comment.receiver.nickname() + '|'
	elif t == "N":
		tls.notes = tls.notes + '|' + comment.author.nickname() if tls.notes != None else comment.author.nickname()
		
	tls.save()
	self.reply({"Success": True, "Comments": tls.comments, "author": users.get_current_user(), "text": comment.text,"created": datetime.datetime.now() })
		
  def getComments(self):
	cs = Comment.all().filter("tiddler = ",self.request.get("tiddlerId"))
	ref = self.request.get("ref")
	if ref != "":
		cs = cs.filter("ref = ", ref)
	xd = XmlDocument()
	tce = xd.add(xd,'TiddlerComments', attrs={'type':'object[]'})
	for ac in cs:
		ace = xd.add(tce,"Comment")
		xd.add(ace, "author","anonymous" if ac.author == None else ac.author.nickname())
		xd.add(ace, "text",ac.text)
		xd.add(ace, "created", ac.created)
		xd.add(ace, "version", ac.version)
		if ref == "":
			xd.add(ace, "ref", ac.ref);
	self.sendXmlResponse(xd)

  def getNotes(self):
	ns = Note.all().filter("tiddler =",self.request.get("tiddlerId")).filter("author =",users.get_current_user())
	xd = XmlDocument()
	tce = xd.add(xd,'TiddlerNotes', attrs={'type':'object[]'})
	for ac in ns:
		ace = xd.add(tce,"Note")
		xd.add(ace, "text",ac.text)
		xd.add(ace, "created", ac.created)
		xd.add(ace, "version", ac.version)
	self.sendXmlResponse(xd)
	
  def getMessages(self):
	ms = Message.all().filter("tiddler =",self.request.get("tiddlerId")).filter("receiver =", users.get_current_user())
	xd = XmlDocument()
	tce = xd.add(xd,'TiddlerMessages', attrs={'type':'object[]'})
	for ac in ms:
		ace = xd.add(tce,"Note")
		xd.add(ace, "author","anonymous" if ac.author == None else ac.author.nickname())
		xd.add(ace, "text",ac.text)
		xd.add(ace, "created", ac.created)
		xd.add(ace, "version", ac.version)
	self.sendXmlResponse(xd)

  def getMacro(self):
	try:
		ftwm = open(path.normcase( self.request.get('macro') + '.js'))
		self.reply({'text': ftwm.read()})
		ftwm.close()
	except Exception,x:
		self.fail(str(x))
	
  def pageProperties(self):
	if users.get_current_user() == None:
		return self.fail("You are not logged in");
	path = self.request.path
	page = self.CurrentPage()
	if page == None:
		if path == "/" and users.get_current_user() != None: # Root page
			page = Page()
			page.gwversion = "2.3"
			page.path = "/"
			page.sub = self.subdomain
			page.title = ""
			page.subtitle = ""
			page.locked = False
			page.anonAccess = 0
			page.authAccess = 0
			page.groupAccess = 2
			page.owner = users.get_current_user()
			page.groups = ""
		else:
			return self.fail("Page does not exist")
	if self.request.get("title") != "": # Put
		if users.get_current_user() != page.owner and users.is_current_user_admin() == False:
			self.fail("You cannot change the properties of this pages")
		else:
			page.title = self.request.get("title")
			page.subtitle = self.request.get("subtitle")
			page.locked = self.request.get("locked") == "true"
			page.anonAccess = Page.access[self.request.get("anonymous")]
			page.authAccess = Page.access[self.request.get("authenticated")]
			page.groupAccess = Page.access[self.request.get("group")]
			page.groups = self.request.get("groups")
			page.put()
			self.reply({"Success": True })
	else: # Get
		self.reply({ 
			"title": page.title,
			"subtitle": page.subtitle,
			"owner": page.owner,
			"locked": page.locked,
			"anonymous": Page.access[page.anonAccess],
			"authenticated": Page.access[page.authAccess],
			"group": Page.access[page.groupAccess],
			"groups": page.groups})

  def getNewAddress(self):
	path = self.request.path
	lsp = path.rfind("/")
	parent = path[0:1+lsp]
	title = self.request.get("title")
	prex = Page.all().filter("path =",parent).filter("title =", title).get()
	if prex != None:
		self.fail("Page already exists")
	npt = title.replace(' ',"_").replace("/","-")
	prex = Page.all().filter("path =",parent + "/" + npt).get()
	if prex != None:
		self.fail("Page already exists")
	self.reply({"Success": True, "Address": npt })
	
  def siteMap(self):
	pal = Page.all().filter('sub',self.subdomain).order('path')
	xd = XmlDocument()
	xroot = xd.add(xd,'SiteMap', attrs={'type':'object[]'})
	for p in pal:
		xpage = xd.createElement("page")
		xroot.appendChild(xpage)
		xd.add(xpage,"path",p.path);
		xd.add(xpage,"title",p.title);
	self.sendXmlResponse(xd)
	
  def createPage(self):
	path = self.request.path
	lsp = path.rfind("/")
	parent = path[0:1+lsp]
	pad = Page.all().filter("path =",parent).get()
	if pad == None: # parent folder doesn't exist
		if self.request.get("title") == "":
			if parent == "/" and users.get_current_user() != None:
				pad = Page()
				pad.gwversion = "2.3"
				pad.path = "/"
				pad.sub = self.subdomain
				pad.owner = users.get_current_user()
				pad.locked = False
				pad.anonAccess = Page.access[self.request.get("anonymous")]
				pad.authAccess = Page.access[self.request.get("authenticated")]
				pad.groupAccess = Page.access[self.request.get("group")]
				pad.put()
				return self.reply( { "Success": True })
			else:
				return self.fail("Root folder not created")
		else:
			return self.fail("Parent folder doesn't exist")
	if users.get_current_user() == None and pad.anonAccess != "":
		return self.fail("You cannot create new pages")

	if self.request.get("defaults") == "get":
		return self.reply({
			"anonymous":Page.access[pad.anonAccess], 
			"authenticated":Page.access[pad.authAccess],
			"group":Page.access[pad.groupAccess] })
	      
	url = parent + self.request.get("address")
	page = Page.all().filter('path =',url).get()
	if page == None:
		page = Page()
		page.gwversion = "2.3"
		page.path = url
		page.sub = self.subdomain
		page.owner = users.get_current_user()
		page.title = self.request.get("title")
		page.subtitle = self.request.get("subtitle")
		page.locked = False
		page.anonAccess = Page.access[self.request.get("anonymous")]
		page.authAccess = Page.access[self.request.get("authenticated")]
		page.groupAccess = Page.access[self.request.get("group")]
		page.put()
		self.SaveNewTiddler(url,"SiteTitle",page.title)
		if page.subtitle != "":
			self.SaveNewTiddler(url,"SiteSubtitle",page.subtitle)
		self.reply( {"Url": url, "Success": True })
	else:
		self.fail("Page already exists: " + page.path)
		
  def getLoginUrl(self):
	# LogEvent("getLoginUrl", self.request.get("path"))
	self.initXmlResponse()
	xd = xml.dom.minidom.Document()
	tv = xd.createElement('LoginUrl')
	if users.get_current_user():
		v = users.create_logout_url("/?method=LoginDone")
	else:
		v = users.create_login_url("/?method=LoginDone&path=" + self.request.get("path"))
	tv.appendChild(xd.createTextNode(v))
	xd.appendChild(tv)
	self.response.out.write(xd.toxml())

  def deletePage(self):
	path = self.request.path
	prex = Page.all().filter("path =",path)
	tls = Tiddler.all().filter("page=",path)
	for result in tls:
		result.delete()
	for result in prex:
		result.delete()
	self.reply({"Success": True})
	
  def getUserName(self):
	self.initXmlResponse()
	xd = xml.dom.minidom.Document()
	tv = xd.createElement('UserName')
	u = users.get_current_user()
	if (u):
		tv.appendChild(xd.createTextNode(u.nickname()))
	xd.appendChild(tv)
	self.response.out.write(xd.toxml())

  def fail(self, msg, aux = None):
	if aux == None:
		aux = {}
	aux["Message"] = msg
	aux["Success"] = False
	self.reply(aux)
	return False

  def warn(self, msg, aux = None):
	if aux == None:
		aux = {}
	aux["Message"] = msg
	aux["Success"] = True
	self.reply(aux)
	return True

  def reply(self, values = { 'Success': True }, de = 'reply'):
	self.initXmlResponse()
	xd = xml.dom.minidom.Document()
	tr = xd.createElement(de)
	xd.appendChild(tr)
	for k, v in values.iteritems():
		av = xd.createElement(k);
		tr.appendChild(av);
		if type(v) == bool:
			av.setAttribute("type","bool")
			v = "true" if v else "false"
		av.appendChild(xd.createTextNode(unicode(v)))
	self.response.out.write(xd.toxml())
	return True
	
  def LoginDone(self,path):
	page = Page.all().filter("path =",path).get()
	# LogEvent('Login', userWho() + path)
	grpaccess = "false"
	if page != None:
		if HasGroupAccess(page.groups,userWho()):
			grpaccess = "true"
			
	self.response.out.write(
'<html>'
'<header><title>Login succeeded</title>'
'<script>'
'function main() { \n'
'	act = "onLogin(\''  + userWho() + '\',\'' + self.request.get("path") + '\',' + grpaccess + ')";'
'	window.parent.setTimeout(act,100);\n'
'}\n'
'</script></header>'
'<body onload="main()">'
'<a href="/">success</a>'
'</body>'
'</html>') #,\'' + self.request.get("path") + '\'

  def getTiddlers(self):
	self.initXmlResponse()
	xd = XmlDocument()
	tr = xd.add(xd,"reply")
	pg = self.request.get("page")
	page = Page.all().filter("path =",pg).get()
	error = None
	if page != None:
		who = userWho()
		if who == '':
			if page.anonAccess < page.ViewAccess:
				error = "You need to log in to access this page"
		elif page.owner.nickname() != who:
			if page.authAccess < page.ViewAccess:
				if page.groupAccess < page.ViewAccess or HasGroupAccess(page.groups,who) == False:
					error = "You do not have access to this page"
			
	if error == None:
		tiddlers = Tiddler.all().filter("page = ", pg).filter("current = ", True)
		if tiddlers.count() > 0:
			tr.setAttribute('type', 'string[]')
			for t in tiddlers:
				xd.add(tr,"tiddler",unicode(t.title))
		else:
			error = "Page '" + pg + "' is empty"
		
	if error != None:
		xd.add(tr,"error",error)
	return self.response.out.write(xd.toxml())

  def getTiddler(self):
	id = self.request.get("id",None)
	if id != None:
		urlParts = id.split('#')
		if len(urlParts) == 2:
			urlPath = urlParts[0]
			urlPick = urlParts[1]
			ts = self.tiddlersFromSources(urlPath)
			if ts != None:
				for at in ts:
					if at.title == urlPick:
						return self.reply( {
							'title': at.title,
							'id': 'include-' + id,
							'text': at.text,
							'modifier': at.author_ip,
							'tags': at.tags })
			self.fail("File or tiddler not found")
		else:
			self.fail("id should be like path#tiddlerTitle")
		
	title = self.request.get("title")
	if title == "":
		url = self.request.get("url").split("#",1)
		if len(url) < 2:
			return LogEvent("getTiddler:", self.request.get("url"))
		title = url[1]
		page = url[0]
	else:
		page = self.request.path
		
	t = Tiddler.all().filter("page", page).filter("title",title).filter("current", True).get()
	if t == None:
		self.reply({"success": False })
	else:
		if t.public or ReadAccessToPage(t.page):
			self.reply({ \
			'success': True, \
			'id': t.id, \
			'title': t.title, \
			'text': t.text, \
			'tags': t.tags, \
			'created': t.created.strftime("%Y%m%d%H%M%S"),
			'modifier': userNameOrAddress(t.author,t.author_ip),
			'modified': t.modified.strftime("%Y%m%d%H%M%S"),
			'version': t.version
			})
		else:
			self.reply({"success": False, "Message": "No access" })
		
  def getGroups(self):
	groups = Group.all().filter("admin =", users.get_current_user())
	self.initXmlResponse()
	xd = xml.dom.minidom.Document()
	tr = xd.createElement("groups")
	tr.setAttribute('type', 'string[]')
	for g in groups:
		av = xd.createElement("group");
		tr.appendChild(av);
		av.appendChild(xd.createTextNode(unicode(g.name)))
	xd.appendChild(tr)
	self.response.out.write(xd.toxml())

  def getRecentChanges(self):
	xd = self.initXmlResponse()
	re = xd.add(xd,'result')
	offset = eval(self.request.get('offset'))
	limit = eval(self.request.get('limit'))
	ts = Tiddler.all().filter("sub",self.subdomain).order("-modified").fetch(limit,offset)
	ta = xd.add(re,"changes",attrs={'type':'object[]'})
	for t in ts:
		rt = xd.add(ta,"tiddler")
		xd.add(rt,"time",t.modified)
		xd.add(rt,"who",t.author)
		xd.add(rt,"page",t.page)
		xd.add(rt,"title",t.title)
	xd.add(re,"Success",True)
	self.sendXmlResponse(xd)

  def getRecentComments(self):
	xd = self.initXmlResponse()
	re = xd.add(xd,'result')
	offset = eval(self.request.get('offset'))
	limit = eval(self.request.get('limit'))
	cs = Comment.all().order("-created").fetch(limit,offset)
	ca = xd.add(re,"comments",attrs={'type':'object[]'})
	dt = dict()
	for ac in cs:
		rt = xd.add(ca,"comment")
		xd.add(rt,"text",ac.text)
		xd.add(rt,"who",ac.author)
		xd.add(rt,"time",ac.created)
		xd.add(rt,"ref",ac.ref)
		xd.add(rt,"tiddler",ac.tiddler)
		if dt.has_key(ac.tiddler) == False:
			dt[ac.tiddler] = Tiddler.all().filter('id',ac.tiddler).filter('current',True).get()
	ta = xd.add(re,"tiddlers",attrs={'type':'object[]'})
	for (id,tn) in dt.iteritems():
		ti = xd.add(ta,"tiddler")
		xd.add(ti,"page",tn.page)
		xd.add(ti,"title",tn.title)
		xd.add(ti,"id",id);
	xd.add(re,"Success",True)
	self.sendXmlResponse(xd)

  def createGroup(self):
	name = self.request.get("name")
	if Group.all().filter("name =", name).get() == None:
		g = Group()
		g.name = name
		g.admin = users.get_current_user()
		g.put()
		self.reply({"Group": name, "Success": True})
	else:
		self.reply({"Message": "A group named " + name + " already exists", "Success": False})
		
  def getGroupMembers(self):
	grp = self.request.get("groupname")
	ms = GroupMember.all().filter("group =",grp).order("name")
	self.initXmlResponse()
	xd = xml.dom.minidom.Document()
	tr = xd.createElement("reply")
	tr.setAttribute('type', 'string[]')
	for am in ms:
		av = xd.createElement("m")
		tr.appendChild(av)
		av.appendChild(xd.createTextNode(unicode(am.name)))
	xd.appendChild(tr)
	self.response.out.write(xd.toxml())
	
  def addGroupMember(self):
	user = self.request.get("user")
	grp = self.request.get("groupname")
	ms = GroupMember.all().filter("group =",grp).filter("name =",user)
	if ms.get() == None:
		nm = GroupMember()
		nm.group = grp
		nm.name = user
		nm.put()
		self.reply({"Success": True})
	else:
		self.reply({"Message": user + " is already a member of " + grp,"Success":False});

  def removeGroupMember(self):
	user = self.request.get("user")
	grp = self.request.get("groupname")
	gmu = GroupMember.all().filter("group =",grp).filter("name =",user).get()
	gmu.delete()
	self.reply({"Success": True})

  def tiddlerChanged(self,et,nt):
	if et.tags != nt.tags:
		self.status = "tags changed: " + et.tags + " <> " + nt.tags
		return True
	if et.text != nt.text:
		self.status = "text changed: " + et.text + " <> " + nt.text
		return True
	if et.title != nt.title:
		self.status =  "title changed: " + et.title + " <> " + nt.title
		return True
	return False  
  
  def uploadTiddlersFrom(self,storeArea):
	page = Page.all().filter("path",self.request.path).get()
	if page == None:
		error = "Page " + nt.page + " doesn't exist (page properties are not undefined)!"
	else:
		error = page.UpdateViolation()
	if error != None:
		self.response.out.write(error)
		return

	self.response.out.write("<ul>");
	for te in storeArea.childNodes:
		# self.response.out.write("<br>&lt;" + (te.tagName if te.nodeType == xml.dom.Node.ELEMENT_NODE else str(te.nodeType)) + "&gt;");
		if te.nodeType == xml.dom.Node.ELEMENT_NODE:
			nt = TiddlerFromXml(te,self.request.path)
			if nt == None:
				return
			nt.public = page.anonAccess > page.NoAccess
			#self.response.out.write("<br>Upload tiddler: " + nt.title + " | " + nt.id + " | version " + str(nt.version) + nt.text + "<br>")
			
			et = Tiddler.all().filter('id',nt.id).filter("current",True).get() if nt.id != "" else None
			if et == None:
				et = Tiddler.all().filter('page',self.request.path).filter('title',nt.title).filter("current",True).get()
				
			# self.response.out.write("Not found " if et == None else ("Found v# " + str(et.version)))
			if et == None:
				self.status = ' - added';
				nt.id = str(uuid.uuid4())
				nt.comments = 0
			elif et.version > nt.version:
				self.response.out.write("<li>" + nt.title + " - version " + str(nt.version) + \
										" <b>not</b> uploaded; it is already at version " + str(et.version) + "</li>")
				continue
			elif self.tiddlerChanged(et,nt):
				nt.id = et.id
				nt.version = nt.version + 1
				nt.comments = et.comments
				et.current = False
				et.put()
			else:
				self.response.out.write("<li>" + nt.title + " - no changes</li>")
				continue
			nt.put()
			self.response.out.write('<li><a href="' + self.request.path + "#" + urllib.quote(nt.title) + '">' + nt.title + "<a> " + self.status + "</li>");
			page.Update(nt)
	self.response.out.write("</ul>");

  def uploadTiddlyWikiDoc(self,filename,filedata):
	try:
		dom = xml.dom.minidom.parseString(filedata)
	except Exception,x:
		self.response.out.write("Oops: " + str(x))
		return
	doce = dom.documentElement
	if doce.tagName == "html":
		for ace in doce.childNodes:
			if ace.nodeType == xml.dom.Node.ELEMENT_NODE and ace.tagName == "body":
				for bce in ace.childNodes:
					if bce.nodeType == xml.dom.Node.ELEMENT_NODE:
						if bce.getAttribute("id") == "storeArea":
							self.uploadTiddlersFrom(bce);
		
  def ImportDb(self,filedata):
	try:
		dom = xml.dom.minidom.parseString(filedata)
		doce = dom.documentElement
		if doce.tagName == "giewiki":
			for ace in doce.childNodes:
				if ace.nodeType == xml.dom.Node.ELEMENT_NODE:
					mc = None
					deleteKey = None
					deleteMatch = None
					if ace.tagName == "tiddlers":
						mc = Tiddler
					elif ace.tagName == "shadowtiddlers":
						mc = ShadowTiddler
					elif ace.tagName == "siteinfos":
						mc = ShadowTiddler
					elif ace.tagName == "pages":
						mc = Page
						deleteKey = "path"
					elif ace.tagName == "comments":
						mc = Comment
					elif ace.tagName == "messages":
						mc = Message
					elif ace.tagName == "notes":
						mc = Note
					elif ace.tagName == "groups":
						mc = Group
					elif ace.tagName == "groupmember":
						mc = GroupMember
					if mc != None:
						for ice in ace.childNodes:
							mi = mc()
							self.response.out.write('<br>class ' + mc.__name__ + '()<br>')
							for mce in ice.childNodes:
								field = mce.tagName
								dtype = mce.getAttribute('type')
								if mce.firstChild != None:
									self.response.out.write(field + '(' + dtype + ') ')
									v = mce.firstChild.nodeValue
									# self.response.out.write(field + str(mce.firstChild.nodeValue))
									if dtype == 'datetime':
										if len(v) == 19:
											v = datetime.datetime.strptime(v,'%Y-%m-%d %H:%M:%S')
										else:
											v = datetime.datetime.strptime(v,'%Y-%m-%d %H:%M:%S.%f')
										setattr(mi,field,v)
									elif dtype == 'long' or dtype == 'int' or dtype == 'bool':
										setattr(mi,field,eval(v))
									elif dtype == 'User':
										setattr(mi,field,users.User(email=v))
									else:
										setattr(mi,field,unicode(v))
								if field == deleteKey:
									deleteMatch = v
							if deleteMatch != None:
								oldrec = mc.all().filter(deleteKey,deleteMatch).get()
								if oldrec != None:
									oldrec.delete()
							mi.put()
				
	except Exception,x:
		self.response.out.write("Oops: " + str(x))
		return

  def uploadFile(self):
	filename = self.request.get("filename")
	filedata = self.request.get("MyFile")
	filetype = Filetype(filename)
	if filename == '_export.xml' and users.is_current_user_admin():
		self.ImportDb(filedata)
	elif filetype == 'twd':
		return self.uploadTiddlyWikiDoc(filename,filedata)
	else:
		f = UploadedFile()
		f.owner = users.get_current_user()
		f.path = CombinePath(self.request.path, filename)
		f.mimetype = self.request.get("mimetype")
		if f.mimetype == None or f.mimetype == "":
			f.mimetype = MimetypeFromFiletype(filetype)
		f.data = db.Blob(filedata)
		f.put()
		u = open('UploadDialog.htm')
		ut = u.read().replace("UFL",leafOfPath(self.request.path) + self.request.get("filename")).replace("UFT",f.mimetype).replace("ULR","Uploaded:")
		self.response.out.write(ut)
		u.close()
	
  def fileList(self):
	files = UploadedFile.all()
	owner = self.request.get("owner")
	if owner != "":
		files = files.filter("owner =",owner)
	path = self.request.get("path")
	xd = self.initXmlResponse()
	re = xd.addArrayOfObjects('result')
	for f in files.fetch(100):
		if path == "" or f.path.find(path) == 0:
			xd.add(re, 'file',f.path,attrs={'mimetype':f.mimetype})
	self.response.out.write(xd.toxml())
	
  def urlFetch(self):
	result = urlfetch.fetch(self.request.get('url'))
	if result.status_code == 200:
		xd = self.initXmlResponse()
		tv = xd.createElement('Content')
		xd.appendChild(tv);
		tv.appendChild(xd.createTextNode(result.content))
		self.response.out.write(xd.toxml())


  def tiddlersFromUrl(self):
	if self.request.get('menu') == 'true':
		filelist = list()
		for file in UrlImport.all():
			filelist.append(file.url)
		return replyWithStringList(self,"files","file",filelist)

	url = self.request.get('url')
	iftagged = self.request.get('filter')
	cache = self.request.get('cache')
	select = self.request.get('select')
	cache = 60 if cache == "" else int(cache) # default cache age: 60 s
	try:
		tiddlers = self.tiddlersFromSources(url,cache=cache,save=True)
		if tiddlers == None:
			return			
	except xml.parsers.expat.ExpatError, ex:
		return self.fail("The url " + url + " failed to read as XML: <br>" + str(ex))
		
	fromUrl = list()
	page = self.CurrentPage()
	if page.systemInclude != None:
		urls = page.systemInclude.split('\n')
		for al in urls:
			if al.startswith(url):
				if select != "":
					urls.remove(al) # to be replaced by select
				else:
					fromUrl = al.split('#')[1].split('||')
	if select != "":
		newPick = url + "#" + select
		if page.systemInclude == None:
			page.systemInclude = newPick
		else:
			urls.append(newPick)
			page.systemInclude = '\n'.join(urls)
		page.put()
		return self.warn("Reload to get the requested tiddlers")

	newlist = list()
	for t in tiddlers:
		if t != None:
			if iftagged == "" or tagInFilter(t.tags,iftagged):
				newel = {'title': t.title, 'tags': t.tags }
				if fromUrl.count(t.title) > 0:
					newel['current'] = 'true'
				newlist.append(newel)

	replyWithObjectList(self,'Content','tnt',newlist)


  def tiddlersFromSources(self,url,sources=None,cache=None,save=False):
	xd = self.XmlFromSources(url,sources)
	if xd.__class__ == xml.dom.minidom.Document:
		pe = xd.documentElement
		if pe.nodeName.lower() == 'html':
			es = pe.getElementsByTagName('body')
			if len(es) == 1:
				pe = es[0]
			else:
				raise ImportException(pe.nodeName + " contains " + str(len(es)) + " body elements.")
		return self.TiddlersFromXml(pe,url)
	return None
	

  def XmlFromSources(self,url,sources=None,cache=None,save=False):
	if url.startswith('//'):
		url = 'http:' + url
	if url.startswith("http:"):
		if sources == None or 'local' in sources:
			importedFile = UrlImport.all().filter('url',url).get()
			if importedFile != None:
				return xml.dom.minidom.parseString(importedFile.data)
		if sources == None or 'remote' in sources:	
			content = memcache.get(url)	if cache != None else None
			if content == None:
				try:
					result = urlfetch.fetch(url)
				except urlfetch.Error, ex:
					raise ImportException("Could not get the file <b>" + url + "</b>:<br/>Exception " + str(ex.__class__.__doc__))
				if result.status_code != 200:
					raise ImportException("Fetching the url " + url + " returned status code " + str(result.status_code))
				else:
					content = result.content
					if cache != None:
						memcache.add(url,content,cache)
			xd = xml.dom.minidom.parseString(content)
			if xd == None:
				return None
			if save:
				urlimport = UrlImport()
				urlimport.url = url
				urlimport.data = db.Blob(content)
				urlimport.put()
			return xd
			
		return None				
	else:
		return xml.dom.minidom.parse(url)


  def TiddlersFromXml(self,te,path):
	list = []

	def append(t):
		if t != None:
			# self.Trace('Append ' + t.title + ' from ' + t.page)
			list.append(t)

	# self.Trace('TiddlersFromXml ' + te.tagName)
	if te.tagName in ('body','document'):
		for acn in te.childNodes:
			if acn.nodeType == xml.dom.Node.ELEMENT_NODE:
				if acn.nodeName == 'storeArea' or acn.getAttribute('id') == 'storeArea':
					for asn in acn.childNodes:
						if asn.nodeType == xml.dom.Node.ELEMENT_NODE and asn.tagName == 'div':
							append(TiddlerFromXml(asn,path))
	elif te.tagName == 'tiddlers':
		for ce in te.childNodes:
			if ce.nodeType == xml.dom.Node.ELEMENT_NODE and ce.tagName == 'div':
				append(TiddlerFromXml(ce,path))
	else:
		append(TiddlerFromXml(te,path))
	return list
	
  def evaluate(self):
	xd = self.initXmlResponse()
	tv = xd.createElement('Result')
	xd.appendChild(tv);
	if  users.is_current_user_admin():
		try:
			result = eval(self.request.get("expression"))
# this syntax was introduced in Python 2.6, and is not supported by the google environment:
#		except Exception as sa:
# in stead, use:
		except Exception, sa:
			result = sa
	else:
		result = "Access denied"
	tv.appendChild(xd.createTextNode(str(result)))
	self.response.out.write(xd.toxml())

  def saveSiteInfo(self):
	xd = self.initXmlResponse()
	tv = xd.createElement('Result')
	xd.appendChild(tv);
	if  users.is_current_user_admin():
		try:
			data = SiteInfo.all().get()
			if data != None:
				data.delete()
			data = SiteInfo()
			data.title = self.request.get("title")
			data.description = self.request.get("description")
			data.put()
			result = "Data was saved"
		except Exception, sa:
			result = sa
	else:
		result = "Access denied"
	tv.appendChild(xd.createTextNode(str(result)))
	self.response.out.write(xd.toxml())

  def publishSub(self):
	npages = toDict(Page.all().filter('sub',self.subdomain).fetch(1000),'path')
	epages = toDict(Page.all().filter('sub',None).fetch(1000),'path')
	results = []
	for pg in npages:
		if not pg.path in epages:
			pg[pg.path].sub = None
			pg.put()
	for t in Tiddler.all().filter('sub',self.subdomain):
		if t.current == True:
			et = Tiddler.all().filter('id',t.id).filter('current',True).filter('sub',None).get()
			if et != None: # demote
				et.current = False
				et.put()
			t.sub = None # promote
			t.put()
			results.append(t.title)
		else:
			t.delete()
	self.reply({'Success': True, 'Message': str(len(results)) + " tiddlers published:<br>" + '<br>'.join(results) })
	
  def expando(self,method):
	xd = self.initXmlResponse()
	result = xd.createElement('Result')
	mt = Tiddler.all().filter("page = ", "/_python/").filter("title = ", method).filter("current = ", True).get()
	if mt == None:
		return self.fail("No such method found: " + method)
	code = compile(mt.text, mt.title, 'exec')
	exec code in globals(), locals()
	if result.childNodes.count > 0:
		xd.appendChild(result)
		self.response.out.write(xd.toxml())

  def truncateAll(self):
	if users.is_current_user_admin():
		truncateAllData()
		self.fail('Data was truncated')
	else:
		self.fail('Access denied')
		
  def getFile(self):
	try:
		ftwm = open(path.normcase( self.request.get('filename')))
		self.reply({'text': ftwm.read()})
		ftwm.close()
	except Exception,x:
		self.fail(str(x))

  def traceMethod(self,m,method):
	r = method()
	if self.trace != False:
		LogEvent("tm:" + m,'\n'.join(self.trace))
	return r

  def post(self):
	trace = memcache.get(self.request.remote_addr)
	self.trace = [] if trace != None and trace != "0" else False
	self.getSubdomain()
	m = self.request.get("method") # what do you want to do
	if m in dir(self):
		try: # find specified method if it's built-in
			method = getattr(self,m)
		except AttributeError, a:
			return self.fail("Invalid method: " + m)
		except MyError, x:
			return self.fail(str(x.value))
		return self.traceMethod(m,method) # run method
	else:
		try: # Any class that has a 'public(self,page)' method handle method named by class
			po = eval(m + "()") # construct class
			method = getattr(po,'public') # does it support the public interface?
			if method != None:
				return method(self) # i.e. po->public(self)
			else:
				return self.expando(m)
		except NameError:
			return self.expando(m)
		except Exception, x:
			return self.fail("Ups!\n" + str(dir(x)))

############################################################################
  def BuildTiddlerDiv(self,xd,id,t,user):
	div = xd.createElement('div')
	div.setAttribute('id', id)
	div.setAttribute('title', t.title)
	if getattr(t,'locked',False):
		div.setAttribute('locked','true')
	elif t.page != self.request.path:
		div.setAttribute('from',t.page)
		div.setAttribute('locked','true')

	if t.modified != None:
		div.setAttribute('modified', t.modified.strftime("%Y%m%d%H%M%S"))
	div.setAttribute('modifier', getAuthor(t))
		
	div.setAttribute('version', str(t.version))
	div.setAttribute('comments', str(t.comments))
	if t.notes != None and user != None:
		if t.notes.find(user.nickname()) >= 0:
			div.setAttribute('notes', "true")
	if t.messages != None and user != None:
		msgCnt = t.messages.count("|" + user.nickname())
		if msgCnt > 0:
			div.setAttribute('messages', str(msgCnt))
	if t.tags != None:
		div.setAttribute('tags', t.tags);
	pre = xd.createElement('pre')
	pre.appendChild(xd.createTextNode(t.text))
	div.appendChild(pre)
	return div

  def cleanup(self):
	for el in EditLock.all():
		until = el.time + timedelta(0,60*eval(str(el.duration)))
		if until < datetime.datetime.utcnow():
			el.delete()
	truncateModel(LogEntry)
	  
  def task(self,method):
	if method == 'cleanup':
		return self.cleanup()
		
  def export(self):
	self.initXmlResponse()
	xd = xml.dom.minidom.Document()
	xr = xd.createElement("giewiki")
	xr.setAttribute('timestamp',str(datetime.datetime.now()))
	xd.appendChild(xr)
	exportTable(xd,xr,Tiddler,'tiddlers','tiddler')
	exportTable(xd,xr,ShadowTiddler,'shadowtiddlers','shadowtiddler')
	exportTable(xd,xr,Page,'pages','page')
	exportTable(xd,xr,Comment,'comments','comment')
	exportTable(xd,xr,Note,'notes','note')
	exportTable(xd,xr,Message,'messages','message')
	exportTable(xd,xr,SiteInfo,'siteinfo','siteinfo')
	exportTable(xd,xr,Group,'groups','group')
	exportTable(xd,xr,GroupMember,'groupmembers','groupmember')
	self.response.out.write(xd.toxml())

  def Trace(self,msg):
	if self.trace == False:
		return # disabled
	if self.trace == None:
		self.trace = []
	self.trace.append(msg)
	
  def CurrentPage(self):
	for page in Page.all().filter("path",self.request.path):
		if page.sub == self.subdomain: # should eventually be filter
			return page
	return None

  def get(self): # this is where it all starts
	trace = self.request.get('trace')
	if trace == '':
		self.trace = False # disabled by default
	else:
		self.traceLevel = self.request.get('trace')
		self.trace = []
		memcache.add(self.request.remote_addr, self.traceLevel, 300) # 5 minutes
		self.Trace("TL=" + memcache.get(self.request.remote_addr))

	self.getSubdomain()
	method = self.request.get("method")
	
	if method == "LoginDone":
		return self.LoginDone(self.request.get("path"))
		
	if self.request.path == "/_tasks":
		return self.task(method)
	elif self.request.path == "/_export.xml" and users.is_current_user_admin():
		return self.export()

	tiddict = dict()
	defaultTiddlers = ""
	self.warnings = ""

	page = self.CurrentPage()
	if page != None and page.gwversion == None:
		Upgrade(self)
		self.warnings = "DataStore was upgraded"
	if page != None:
		if page.systemInclude != None:
			includeDisabled = self.request.get('disable')
			if includeDisabled != '*':
				for sf in page.systemInclude.split('\n'):
					urlParts = sf.split('#')
					urlPath = urlParts[0]
					if includeDisabled != urlPath:
						urlPicks = None if len(urlParts) <= 1 else urlParts[1].split('||')
						tds = self.tiddlersFromSources(urlPath)
						if tds != None:
							for tdo in tds:
								if urlPicks == None or urlPicks.count(tdo.title) > 0:
									if tdo.id == None or tdo.id == '':
										tdo.id = 'include-' + urlPath + '#' + tdo.title
									tiddict[tdo.id] = tdo

	includeNumber = 0
	includefiles = self.request.get("include").split()
	if self.subdomain != None:
		includefiles.append('PublishPlugin.xml')
	for tn in includefiles:
		try:
			splitpos = tn.find('|')
			if splitpos > 0: # rule: filename|select-list
				tfs = tn[splitpos + 1:].split('|') # the filter: ta|tb|...
				tn = tn[0:splitpos] # the filename
			else:
				tfs = None
			tds = self.tiddlersFromSources(tn)
			tdx = []
			for tdo in tds:
				if tdo == None:
					self.warnings = "None in TiddlersFromXml<br>";
				elif tfs == None or tdo.title in tfs:
					includeNumber = includeNumber - 1
					tiddict['include' + str(includeNumber)] = tdo
					if tfs != None:
						tfs.remove(tdo.title)
				else:
					tdx.append(tdo.title)
			if tfs != None and len(tfs) > 0:
				if tfs[0] != 'list':
					self.warnings = "Not found: " + '|'.join(tfs)
				elif len(tdx) > 0:
					self.warnings = "Found but excluded:<br>" + ' '.join(tdx)
		except Exception, x:
			self.response.out.write("<html>Error including " + tn + ":<br>" + str(x))
			return
	
	for st in ShadowTiddler.all():
		if self.request.path.startswith(st.path):
			tiddict[st.tiddler.id] = st.tiddler
	
	tiddlers = Tiddler.all().filter("page", self.request.path).filter("sub",self.subdomain).filter("current", True)
		
	mergeDict(tiddict, tiddlers)
	
	if self.merge == True:
		tiddlers = Tiddler.all().filter("page", self.request.path).filter("sub",None).filter("current", True)
		mergeDict(tiddict,tiddlers)
	
	includes = Include.all().filter("page", self.request.path)
	for t in includes:
		tv = t.version
		tq = Tiddler.all().filter("id = ", t.id)
		if t.version == None:
			tq = tq.filter("current = ", True)
		else:
			tq = tq.filter("version = ", tv)
		t = tq.get()
		if t != None:
			id = t.id
			if id in tiddict:
				if t.version > tiddict[id].version:
					tiddict[id] = t
			else:
				tiddict[id] = t

	httpMethodTiddler = None
	for id, t in tiddict.iteritems():
		if t == None:
			print("Bad data in tiddict: " + str(id))
			return
		if t.title == 'HttpMethods':
			httpMethodTiddler = tiddict.pop(id)
			break
		
	# LogEvent("get: " + str(len(tiddict)) , self.request.path)
	pages = []
	if len(tiddict) == 0: # Not an existing page, perhaps an uploaded file ?
		file = UploadedFile.all().filter("path =", self.request.path).get()
		LogEvent("Get file", self.request.path)
		if file != None:
			self.response.headers['Content-Type'] = file.mimetype
			self.response.headers['Cache-Control'] = 'no-cache'
			self.response.out.write(file.data)
			return
		else:
			LogEvent("No file", self.request.path)
	else: # list pages next to this
		papalen = self.request.path.rfind('/')
		if papalen == -1:
			paw = "";
		else:
			paw = self.request.path[0:papalen + 1]
		for p in Page.all():
			if p.path.startswith(paw):
				pages.append(p)
		
	user = users.get_current_user()
	if user != None:
		username = user.nickname()
	else:
		username = ""
	
	twd = self.request.get('twd',None)
	xsl = self.request.get('xsl',None)
	if twd == None and xsl == None:	# Unless a TiddlyWiki is required or a style sheet is specified
		xsl = "/static/iewiki.xsl"	# use the default,

	xd = self.initXmlResponse()
	if xsl != None and xsl != "":	# except if no CSS is desired
		xd.appendChild(xd.createProcessingInstruction('xml-stylesheet','type="text/xsl" href="' + xsl + '"'))

	elDoc = xd.createElement("document")
	xd.appendChild(elDoc)
		
	if twd == None: # normal giewiki output
		elStArea = xd.createElement("storeArea")
		elShArea = xd.createElement("shadowArea")
		metaDiv = xd.createElement('div')
		metaDiv.setAttribute('title', "_MetaData")
		metaDiv.setAttribute('admin', 'true' if users.is_current_user_admin() else 'false')
		metaDiv.setAttribute('clientip', self.request.remote_addr)
		if page != None:
			metaDiv.setAttribute('timestamp',str(datetime.datetime.now()))
			metaDiv.setAttribute('username',username)
			metaDiv.setAttribute('owner', page.owner.nickname())
			metaDiv.setAttribute('access', AccessToPage(page,user))
			metaDiv.setAttribute('anonaccess',page.access[page.anonAccess]);
			metaDiv.setAttribute('authaccess',page.access[page.authAccess]);
			metaDiv.setAttribute('groupaccess',page.access[page.groupAccess]);
			if page.groups != None:
				metaDiv.setAttribute('groups',page.groups);
				if (page.groupAccess > page.ViewAccess) and HasGroupAccess(page.groups,username):
					metaDiv.setAttribute('groupmember','true')
			if page.locked:
				metaDiv.setAttribute('locked','true')
			if self.warnings != "":
				metaDiv.setAttribute('warnings',self.warnings)
		if self.trace != None and self.trace != False and len(self.trace) > 0:
			metaPre = xd.createElement('pre')
			metaDiv.appendChild(metaPre)
			metaPre.appendChild(xd.createTextNode('\n'.join(self.trace)))
		elStArea.appendChild(metaDiv)
		
		pgse = xd.createElement("div")
		metaDiv.appendChild(pgse);
		pgse.setAttribute('title',"pages")
		for p in pages:
			xpage = xd.createElement("a")
			pgse.appendChild(xpage)
			xpage.setAttribute('title',"page")
			xpage.setAttribute('href', p.path);
			xpage.appendChild(xd.createTextNode(p.subtitle))

		if page == None and user == None: # Main page not defined
			defaultTiddlers = "LoginDialog"
			td = Tiddler()
			td.title = "DefaultTiddlers"
			td.version = 0
			td.text = defaultTiddlers
			tiddict["DefaultTiddlers"] = td
			
	else: # TiddlyWiki output
		self.response.headers['Content-Type'] = 'text/html'
		elStArea = xd.createElement("div")
		elStArea.setAttribute("id",'storeArea')
		elShArea = xd.createElement("div")
		elShArea.setAttribute("id",'shadowArea')

	elDoc.appendChild(elStArea) # the root element
	elDoc.appendChild(elShArea)
	
	if ReadAccessToPage(page,user):
		httpMethods = [ httpMethodTiddler.text ] if httpMethodTiddler != None else None
		for id, t in tiddict.iteritems():
			# pages at /_python/ are executable script...
			if t.page.startswith("/_python/") and t.page != self.request.path:
				# ...either to be called from a http (XmlHttpRequest) method
				if t.tags == 'HttpMethod':
					if httpMethods != None:
						httpMethods.append(t.title)
					else:
						t.text = "No proxy for:\n"
					t.text= "{{{\n" + t.text + "\n}}}"
				else: # ...or immediately
					try:
						if t.tags == "test":
							text = "{{{\n" + t.text + "\n}}}\n"
						code = compile(t.text, t.title, 'exec')
						exec code in globals(), locals()
						if t.tags == "test":
							t.text = text + t.text
					except Exception, x:
						t.text = str(x)

			if t.tags != None and "shadowTiddler" in t.tags.split():
				if t.page != self.request.path: # remove tag if not the source page
					tags = t.tags.split()
					tags.remove("shadowTiddler")
					t.tags = ' '.join(tags)
				elShArea.appendChild(self.BuildTiddlerDiv(xd,id,t,user))
			else:
				elStArea.appendChild(self.BuildTiddlerDiv(xd,id,t,user))

		if httpMethods != None:
			httpMethodTiddler.text = '\n'.join(httpMethods)
			elStArea.appendChild(self.BuildTiddlerDiv(xd,httpMethodTiddler.id,httpMethodTiddler,user))

	text = xd.toxml()
	if twd != None:
		twdtext = None
		if twd.startswith('http:'):
			try:
				twdres = urlfetch.fetch(twd)
				if twdres.status_code == 200:
					twdtext = twdres.content
				else:
					text = HtmlErrorMessage("Failed to retrieve " + twd + ":\nHTTP Error " + str(twdres.status_code))
			except Exception, x:
				text = HtmlErrorMessage("Cannot retrive " + str(twd) + ":\n" + str(x))
		else:
			try:
				ftwd = open(twd)
				twdtext = ftwd.read()
				ftwd.close()
			except Exception, x:
				text = HtmlErrorMessage("Cannot read " + twd + ":\n" + str(x))
		if twdtext != None:
			xmldecl = '<?xml version="1.0" ?>' # strip off this
			if text.startswith(xmldecl):
				text = text[len(xmldecl):]
			cssa = '<div id="shadowArea">';
			mysa = elShArea.toxml()
			if len(mysa) > len(cssa) + 6:
				text = text.replace(cssa,mysa[:-6])
			text = twdtext.replace('<div id="storeArea">\n</div>',elStArea.toxml()) # insert text into body
		
	# last, but no least
	self.response.out.write(text)
	if self.trace != False:
		LogEvent("get " + self.request.url,'\n'.join(self.trace))
		self.trace = False	
############################################################################

application = webapp.WSGIApplication( [('/.*', MainPage)], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
