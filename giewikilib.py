# this:	giewikilib.py
# by:	Poul Staugaard
# URL:	http://code.google.com/p/giewiki
# ver.:	1.3.0

import xml.dom.minidom
import datetime

from google.appengine.api import users

from Tiddler import *

class MyError(Exception):
  def __init__(self, value):
	self.value = value
  def __str__(self):
	return repr(self.value)

def htmlEncode(s):
	return s.replace('"','&quot;').replace('<','&lt;').replace('>','&gt;').replace('\n','<br>')

def HtmlErrorMessage(msg):
	return "<html><body>" + htmlEncode(msg) + "</body></html>" 

def Filetype(filename):
	fp = filename.rsplit('.',1)
	if len(fp) == 1:
		return None
	else:
		return fp[1].lower()

def MimetypeFromFiletype(ft):
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

def leafOfPath(path):
	lp = path.rfind('/')
	if lp + 1 < len(path):
		return path[lp + 1:] + '/'
	return ""

def userWho():
	u = users.get_current_user()
	if (u):
		return u.nickname()
	else:
		return ""

def userNameOrAddress(u,a):
	if u != None:
		return u.nickname()
	else:
		return a

def toDict(iter,keyName):
	d = dict()
	for e in iter:
		keyVal = getattr(e,keyName)
		d[keyVal] = e
	return d
	
def tagInFilter(tags,filter):
	tags = tags.split()
	filter = filter.split()
	for t in tags:
		for f in filter:
			if t == f:
				return True
	return False

def xmlArrayOfStrings(xd,te,text,name):
	if isinstance(text,basestring):
		text = text.split()
	for a in text:
		se = xd.createElement(name)
		te.appendChild(se)
		se.appendChild(xd.createTextNode(unicode(a)))
	te.setAttribute('type', 'string[]')

def replyWithStringList(cl,re,se,sl):
	xd = cl.initXmlResponse()
	tv = xd.createElement(re)
	xd.appendChild(tv)
	xmlArrayOfStrings(xd,tv,sl,se)
	cl.response.out.write(xd.toxml())

def getAuthor(t):
	if t.author != None:
		return str(t.author.nickname());
	elif t.author_ip != None:
		return str(t.author_ip)
	else:
		return "?"

def LogEvent(what,text):
	le = LogEntry()
	le.what = str(what)
	le.text = str(text)
	le.put()

def exportTable(xd,xr,c,wnn,enn):
	tr = xd.createElement(wnn)
	xr.appendChild(tr)

	cursor = None
	repeat = True
	while repeat:
		ts = c.all()
		if cursor != None:
			ts.with_cursor(cursor)
		n = 0
		for t in ts.fetch(1000):
			d = dict()
			t.todict(d)
			te = xd.createElement(enn)
			tr.appendChild(te)
			for (tan,tav) in d.iteritems():
				if tav == None:
					continue
				tae = xd.createElement(tan)
				te.appendChild(tae)
				if tav.__class__ != unicode:
					tae.setAttribute('type',unicode(tav.__class__.__name__))
				tae.appendChild(xd.createTextNode(unicode(tav)))
			n = n + 1
		if n < 1000:
			repeat = False
		else:
			cursor = ts.cursor()
	
def mergeDict(td,ts):
	for t in ts:
		id = t.id
		if id in td:
			if t.version > td[id].version:
				td[id] = t
		else:
			td[id] = t

def TiddlersFromXml(te,path):
	list = []
	if te.tagName == 'body':
		for acn in te.childNodes:
			if acn.nodeType == xml.dom.Node.ELEMENT_NODE:
				if acn.getAttribute('id') == 'storeArea':
					for asn in acn.childNodes:
						if asn.nodeType == xml.dom.Node.ELEMENT_NODE and asn.tagName == 'div':
							list.append(TiddlerFromXml(asn,path))

	elif te.tagName == 'tiddlers':
		for ce in te.childNodes:
			if ce.nodeType == xml.dom.Node.ELEMENT_NODE and ce.tagName == 'div':
				list.append(TiddlerFromXml(ce,path))

	else:
		list.append(TiddlerFromXml(te,path))

	return list

def TiddlerFromXml(te,path):
	id = None
	try:
		title = te.getAttribute('title')
		id = te.getAttribute('id')
		author_ip = te.getAttribute('modifier')
		v = te.getAttribute('version')
		version = eval(v) if v != None and v != "" else 1
	except Exception, x:
		print(str(x))
		return None
		
	nt = Tiddler(page = path, title = title, id = id, version = version, author_ip = author_ip)
	nt.current = True
	nt.tags = te.getAttribute('tags')
	nt.author = users.get_current_user()
	for ce in te.childNodes:
		if ce.nodeType == xml.dom.Node.ELEMENT_NODE and ce.tagName == 'pre':
			if ce.firstChild != None and ce.firstChild.nodeValue != None:
				nt.text = ce.firstChild.nodeValue
				break
	if nt.text == None:
		nt.text = ""
	return nt

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
