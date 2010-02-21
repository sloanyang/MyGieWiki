import cgi
import uuid
import xml.dom.minidom
import datetime

from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db
from google.appengine.api import urlfetch 

class MyError(Exception):
  def __init__(self, value):
	self.value = value
  def __str__(self):
	return repr(self.value)

def htmlEncode(s):
	s = s.replace('"','&quot;')
	s = s.replace('<','&lt;')
	s = s.replace('>','&gt;')
	return s

def MimetypeFromFilename(fn):
	fp = fn.rsplit('.',1)
	if len(fp) == 1:
		return "application/octet-stream"
	ft = fp[1].lower()
	if ft == "txt":
		return "text/plain"
	if ft == "htm" or ft == "html":
		return "text/html"
	if ft == "xml":
		return "text/xml"
	if ft == "jpg" or ft == "jpeg":
		return "image/jpeg"
	if ft == "gif":
		return "image/gif"
	return "application/octet-stream"
	
def CombinePath(path,fn):
	if path.rfind('/') != len(path) - 1:
		path = path + '/'
	return path + fn

def HasGroupAccess(grps,user):
	if grps != None:
		for ga in grps.split(","):
			if GroupMember.all().filter("group =",ga).filter("name =",user).get():
				return True
	return False
	
def userWho():
	u = users.get_current_user()
	if (u):
		return u.nickname()
	else:
		return ''

def xmlArrayOfStrings(xd,te,text,name):
  mas = text.split()
  for a in mas:
	se = xd.createElement(name)
	te.appendChild(se)
	se.appendChild(xd.createTextNode(unicode(a)))
  te.setAttribute('type', 'string[]')

class Tiddler(db.Model):
  title = db.StringProperty()
  page = db.StringProperty()
  author = db.UserProperty()
  version = db.IntegerProperty()
  current = db.BooleanProperty()
  text = db.TextProperty()
  created = db.DateTimeProperty(auto_now_add=True)
  modified = db.DateTimeProperty(auto_now_add=True)
  tags = db.StringProperty()
  id = db.StringProperty()
  comments = db.IntegerProperty(0)
  messages = db.StringProperty()
  notes = db.StringProperty()

class Page(db.Model):
  NoAccess = 0
  ViewAccess = 2
  CommentAccess = 4
  AddAccess = 6
  EditAccess = 8
  AllAccess = 10
  access = { "all":10, "edit":8, "add":6, "comment":4, "view":2, "none":0,
             10:"all", 8:"edit", 6:"add", 4:"comment", 2:"view", 0:"none" }
    
  path = db.StringProperty()
  owner = db.UserProperty()
  title = db.StringProperty()
  subtitle = db.StringProperty()
  locked = db.BooleanProperty()
  anonAccess = db.IntegerProperty()
  authAccess = db.IntegerProperty()
  groupAccess = db.IntegerProperty()
  groups = db.StringProperty()

class Comment(db.Model):
  tiddler = db.StringProperty()
  version = db.IntegerProperty()
  text = db.TextProperty()
  created = db.DateTimeProperty(auto_now_add=True)
  author = db.UserProperty()
  ref = db.StringProperty()

class Include(db.Model):
  page = db.StringProperty()
  id = db.StringProperty()
  version = db.IntegerProperty()
  
class Note(Comment):
  revision = db.IntegerProperty()
  
class Message(Comment):
  receiver = db.UserProperty()

class Group(db.Model):
  name = db.StringProperty()
  admin = db.UserProperty()
  
class GroupMember(db.Model):
  name = db.StringProperty()
  group = db.StringProperty()

class UploadedFile(db.Model):
  owner = db.UserProperty()
  path = db.StringProperty()
  mimetype = db.StringProperty()
  data = db.BlobProperty()
  date = db.DateTimeProperty(auto_now_add=True)
  
class LogEntry(db.Model):
	when = db.DateTimeProperty(auto_now_add=True)
	what = db.StringProperty()
	text = db.StringProperty()
	
def LogEvent(what,text):
	le = LogEntry()
	le.what = what
	le.text = text
	le.put()

class XmlDocument(xml.dom.minidom.Document):
	def add(self,parent,name,text=None,attrs=None):
		e = self.createElement(name);
		parent.appendChild(e);
		if attrs != None:
			for n,v in attrs.iteritems():
				e.setAttribute(n,str(v))
		if text != None:
			e.appendChild(self.createTextNode(unicode(text)))
		return e;
	def addArrayOfObjects(self,name,parent=None):
		if parent == None:
			parent = self
		return self.add(parent,name, attrs={'type':'object[]'})
	

class MainPage(webapp.RequestHandler):
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
	p.author = users.get_current_user()
	p.version = 1
	p.comments = 0
	p.current = True
	p.title = name
	p.text = value
	p.tags = ""
	p.id = str(uuid.uuid4())
	p.save()
	
  def saveTiddler(self):
	page = Page.all().filter("path =",self.request.path).get()
	if page == None:
		return self.fail("Page does not exist: " + self.request.path);
	if users.get_current_user() == None and page.anonAccess < 6:
		return self.fail("You cannot change this page")
	if users.get_current_user() != page.owner and page.authAccess < 6 and (page.groupAccess < 6 or HasGroupAccess(page.groups,userWho()) == False):
		return self.fail("Edit access is restricted")

	tlr = Tiddler()
	tlr.page = self.request.path
	tlr.title = self.request.get("tiddlerName")
	tlr.text = self.request.get("text")
	tlr.tags = self.request.get("tags")
	tlr.version = eval(self.request.get("version"))
	tlr.id = self.request.get("tiddlerId")
	tlr.comments = 0
	if (tlr.id == ""):
		tlr.id = str(uuid.uuid4())
	if users.get_current_user():
		tlr.author = users.get_current_user()
	else:
		tlr.authorName = self.request.get("modifier") # shouldn't really be allowed

	tls = Tiddler.all().filter('id = ', tlr.id).filter('version >= ',tlr.version - 1)
	
	versions = self.request.get("versions")
	getPrior = False
	if versions == '':
		getPrior = True
		versions = self.initHist(tlr.title);
	for atl in tls:
		if getPrior or atl.version == tlr.version:
			versions = versions + "|" + atl.modified.strftime("%Y-%m-%d %H:%M") + "|" + atl.author.nickname() + "|" + str(atl.version) + '|<<revision "' + atl.title + '" ' + str(atl.version) + '>>|\n'
		if atl.version >= tlr.version:
			tlr.version = atl.version + 1
			tlr.comments = atl.comments;
		if atl.current:
			atl.current = False
			tlr.comments = atl.comments
			atl.put()
	tlr.current = True
	tlr.put()
	if tlr.tags == "includes":
		tls = tlr.text.split("\n")
		for tlx in tls:
			if tlx.startswith("[[") and tlx.endswith("]]"):
				tli = tlx.lstrip('[').rstrip(']').split("|")
				if tli.count > 1:
					parts = tli[1].split("#")
					ltlx = Tiddler.all().filter("page = ", parts[0]).filter("title = ", parts[1]).filter("current = ",True)
					tlxs = ltlx.fetch(1)
					for tly in tlxs:
						incl = Include()
						incl.page = tlr.page
						incl.id = tly.id
						incl.version = tly.version
						incl.put()
	
	xd = self.initXmlResponse()
	esr = xd.add(xd,'SaveResp')
	xd.appendChild(esr)
	we = xd.createElement('when')
	we.setAttribute('type','datetime')
	we.appendChild(xd.createTextNode(tlr.modified.strftime("%Y%m%d%H%M%S")))
	ide = xd.createElement('id')
	ide.appendChild(xd.createTextNode(str(tlr.id)))

	versions = versions + "|" + tlr.modified.strftime("%Y-%m-%d %H:%M") + "|" + tlr.author.nickname() + "|" + str(tlr.version) + '|<<revision "' + tlr.title + '" ' + str(tlr.version) + '>>|\n'
	ve = xd.createElement('versions')
	ve.appendChild(xd.createTextNode(versions))
	esr.appendChild(we)
	esr.appendChild(ide)
	esr.appendChild(ve)
	self.response.out.write(xd.toxml())

  def tiddlerHistory(self):
	xd = self.initXmlResponse()
	tls = Tiddler.all().filter("id = ", self.request.get("tiddlerId"))
	eHist = xd.add(xd,'Hist')
	eVersions = xd.createElement('versions')
	eHist.appendChild(eVersions)
	text = ""
	for tlr in tls:
		if text == "":
			text = self.initHist(tlr.title);
		text += "|" + tlr.modified.strftime("%Y-%m-%d %H:%M") + "|" + tlr.author.nickname() + "|" + str(tlr.version) + '|<<revision "' + htmlEncode(tlr.title) + '" ' + str(tlr.version) + '>>|\n'
	
	eVersions.appendChild(xd.createTextNode(text))
	self.response.out.write(xd.toxml())

  def tiddlerVersion(self):
	self.initXmlResponse()
	tls = Tiddler.all().filter('id = ', self.request.get("tiddlerId")).filter('version = ',int(self.request.get("version")))
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
		te.appendChild(xd.createTextNode(tlr.author.nickname()))

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
	tls = Tiddler.all().filter('id = ', self.request.get("tiddlerId"))
	any = False
	for tlr in tls:
		tlr.delete()
		any = True
		
	xd = xml.dom.minidom.Document()
	tv = xd.createElement('TiddlerDelete')
	xd.appendChild(tv)
	self.response.out.write(xd.toxml())
	
  def add(self):
	self.reply({"Success": True, "result": int(self.request.get("a")) + int(self.request.get("b"))})
	

  def submitComment(self):
	tls = Tiddler.all().filter('id = ', self.request.get("tiddler")).filter('current == ',True).get()
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
	
	
  def pageProperties(self):
	if users.get_current_user() == None:
		return self.fail("You are not logged in");
	path = self.request.path
	page = Page.all().filter("path =",path).get()
	if page == None:
		if path == "/" and users.get_current_user() != None: # Root page
			page = Page()
			page.path = "/"
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
		if users.get_current_user() != page.owner:
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
	pal = Page.all().order('path')
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
				pad.path = "/"
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
		page.path = url
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

  def fail(self, msg):
	self.reply( {"Message": msg, "Success": False})

  def reply(self, values, de="reply"):
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

  def Eval(self):
	res = eval(self.request.get("expression"))
	self.reply({"value":res})

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
	url = self.request.get("url").split("#",1)
	t = Tiddler.all().filter("page = ", url[0]).filter("title = ",url[1]).filter("current = ", True).get()
	if t == None:
		self.reply({"success": False, "Message": "No such tiddler!" })
	else:
		self.reply({"success": True, "text": t.text })
		
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
	ts = Tiddler.all().order("-modified").fetch(10)
	ta = xd.add(re,"changes",attrs={'type':'object[]'})
	for t in ts:
		rt = xd.add(ta,"tiddler")
		xd.add(rt,"time",t.modified)
		xd.add(rt,"who",t.author)
		xd.add(rt,"page",t.page)
		xd.add(rt,"title",t.title)
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
	
  def uploadFile(self):
	f = UploadedFile()
	f.owner = users.get_current_user()
	f.path = CombinePath(self.request.path, self.request.get("filename"))
	f.mimetype = self.request.get("mimetype")
	if f.mimetype == None or f.mimetype == "":
		f.mimetype = MimetypeFromFilename(self.request.get("filename"))
	f.data = db.Blob(self.request.get("MyFile"))
	f.put()
	u = open('UploadDialog.htm')
	ut = u.read().replace("UFL",self.request.get("filename")).replace("UFT",f.mimetype).replace("ULR","Uploaded:")
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
	result = urlfetch.fetch(self.request.get("url"))
	if result.status_code == 200:
		xd = self.initXmlResponse()
		tv = xd.createElement('Content')
		xd.appendChild(tv);
		tv.appendChild(xd.createTextNode(result.content))
		self.response.out.write(xd.toxml())
		
  def evaluate(self):
	result = eval(self.request.get("expression"))
	xd = self.initXmlResponse()
	tv = xd.createElement('Result')
	xd.appendChild(tv);
	tv.appendChild(xd.createTextNode(format(result)))
	self.response.out.write(xd.toxml())

  def post(self):
	try:
		m = self.request.get("method")
		method = getattr(self,m)
	except AttributeError:
		return self.fail("Invalid method: " + m)
	#except MyError as x:
	#	return self.fail(str(x.value))
	return method()

#lm = str(self.request.path) + "<br>"
#for an in self.request.arguments():
#	av = self.request.get(an)
#	lm = lm + an + " = " + av + "<br>"
#LogEvent("request",lm)

  def get(self):
	method = self.request.get("method")

	if method == "LoginDone":
		self.LoginDone(self.request.get("path"))
		return
		
	tiddict = dict()
	defaultTiddlers = ""
	page = Page.all().filter("path =",self.request.path).get()
	tiddlers = Tiddler.all().filter("page = ", self.request.path).filter("current = ", True)
	for t in tiddlers:
		id = t.id
		if id in tiddict:
			if t.version > tiddict[id].version:
				tiddict[id] = t
		else:
			tiddict[id] = t

	includes = Include.all().filter("page = ", self.request.path)
	for t in includes:
		tv = t.version
		tiddlers = Tiddler.all().filter("id = ", t.id).filter("version = ", tv)
		for t in tiddlers:
			id = t.id
			if id in tiddict:
				if t.version > tiddict[id].version:
					tiddict[id] = t
			else:
				tiddict[id] = t
	
	# LogEvent("get: " + str(len(tiddict)) , self.request.path)
	if len(tiddict) == 0:
		file = UploadedFile.all().filter("path =", self.request.path).get()
		LogEvent("Get file", self.request.path)
		if file != None:
			self.response.headers['Content-Type'] = file.mimetype
			self.response.headers['Cache-Control'] = 'no-cache'
			self.response.out.write(file.data)
			return
		else:
			LogEvent("No file", self.request.path)
	# else:
	# 	LogEvent("Why","not")

	xd = self.initXmlResponse()
	pi = xd.createProcessingInstruction('xml-stylesheet','type="text/xsl" href="/static/iewiki.xsl"')
	xd.appendChild(pi)
	sr = xd.createElement("storeArea")
	xd.appendChild(sr)
	div = xd.createElement('div')
	div.setAttribute('title', "_AccessInfo")

	u = users.get_current_user()
	if u != None:
		username = u.nickname()
		div.setAttribute('username',username)
	else:
		username = ""
		
	if page != None:
		div.setAttribute('owner', page.owner.nickname())
		div.setAttribute('anonaccess',page.access[page.anonAccess]);
		div.setAttribute('authaccess',page.access[page.authAccess]);
		div.setAttribute('groupaccess',page.access[page.groupAccess]);
		if page.groups != None:
			div.setAttribute('groups',page.groups);
			if (page.groupAccess > page.ViewAccess) and HasGroupAccess(page.groups,username):
				div.setAttribute('groupmember','true')
	sr.appendChild(div)
	if page == None and u == None: # Main page not defined
		defaultTiddlers = "LoginDialog"
		td = Tiddler()
		td.title = "DefaultTiddlers"
		td.version = 0
		td.text = defaultTiddlers
		tiddict["DefaultTiddlers"] = td
		
	if page != None and (page.anonAccess >= page.ViewAccess or (u != None and (page.authAccess >= page.ViewAccess) or (page.owner.nickname() == username) or ((page.groupAccess >= page.ViewAccess) and HasGroupAccess(page.groups,username)))):
		# 
		for id, t in tiddict.iteritems():
			div = xd.createElement('div')
			div.setAttribute('id', id)
			div.setAttribute('title', t.title)
			if t.modified != None:
				div.setAttribute('modified', t.modified.strftime("%Y%m%d%H%M%S"))
			if t.author != None:
				div.setAttribute('modifier', t.author.nickname())
			div.setAttribute('version', str(t.version))
			div.setAttribute('comments', str(t.comments))
			if t.notes != None and u != None:
				if t.notes.find(u.nickname()) >= 0:
					div.setAttribute('notes', "true")
			if t.messages != None and u != None:
				msgCnt = t.messages.count("|" + u.nickname())
				if msgCnt > 0:
					div.setAttribute('messages', str(msgCnt))
			if t.tags != None:
				div.setAttribute('tags', t.tags);
			pre = xd.createElement('pre')
			pre.appendChild(xd.createTextNode(t.text))
			div.appendChild(pre)
			sr.appendChild(div)
		
	self.response.out.write(xd.toxml())


application = webapp.WSGIApplication( [('/.*', MainPage)], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
