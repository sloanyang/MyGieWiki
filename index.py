import cgi
import uuid
import urllib
import xml.sax.saxutils
import datetime

from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db
from google.appengine.api import urlfetch 

class SiteInfo(db.Model):
  title = db.StringProperty()
  description = db.StringProperty()
  language = db.StringProperty()

class Page(db.Model):
  path = db.StringProperty()
  title = db.StringProperty()
  subtitle = db.StringProperty()

class Tiddler(db.Model):
  title = db.StringProperty()
  page = db.StringProperty()
  author = db.UserProperty()
  version = db.IntegerProperty()
  current = db.BooleanProperty()
  public = db.BooleanProperty()
  text = db.TextProperty()
  created = db.DateTimeProperty(auto_now_add=True)
  modified = db.DateTimeProperty(auto_now_add=True)
  tags = db.StringProperty()
  id = db.StringProperty()
  comments = db.IntegerProperty(0)
  messages = db.StringProperty()
  notes = db.StringProperty()

class MainRss(webapp.RequestHandler):
  def get(self):
	ignore = ['SiteTitle','SiteSubtitle','MainMenu','GettingStarted']
	si = SiteInfo.all().get()
	if si == None:
		si = SiteInfo()
		tnr = Page.all().filter("path = ", '/').get()
		if tnr != None:
			si.title = tnr.title
			si.description = tnr.subtitle
			si.language = "en"
			
	tq = Tiddler.all().filter("public",True).filter("current",True)
	for tn in ignore:
		tq = tq.filter("title != ", tn)
		
	ts = tq.order("title").order("-modified").fetch(10)
	authors = set()
	for t in ts:
		if t.author != None:
			authors.add(t.author)

	if len(authors) > 0:
		aux = authors.pop()
		copyright = "Copyright " + t.modified.strftime("%Y") + " " + aux.nickname()
		pdate = t.modified
		for aux in authors:
			copyright = copyright + ", " + aux.nickname()
			if pdate < aux.modified:
				pdate = aux.modified
	else:
		copyright = ""
		pdate = datetime.datetime.now()
	
	self.response.out.write('\
<?xml version="1.0"?>\
<rss version="2.0">\
<channel>\
<title>' + xml.sax.saxutils.escape(si.title) + '</title>\
<link>' + self.tiddlerUrl(None) + '</link>\
<description>' + xml.sax.saxutils.escape(si.description) + '</description>\
<language>si.language</language>\
<copyright>' + copyright + '</copyright>\
<pubDate>' + pdate.strftime("%Y-%m-%d") + '</pubDate>\
<lastBuildDate>' + pdate.strftime("%Y-%m-%d") + '</lastBuildDate>\
<docs>http://blogs.law.harvard.edu/tech/rss</docs>\
<generator>GieWiki 1.0.3</generator>')

	for t in ts:
		self.response.out.write('\
<item>\
  <title>' + xml.sax.saxutils.escape(t.title) + '</title>\
  <link>' + self.tiddlerUrl(t) + '</link>\
  <description>' + xml.sax.saxutils.escape(t.text) + '</description>\
  <pubDate>' + xml.sax.saxutils.escape(t.modified.strftime("%Y-%m-%dT%H:%M:%S")) + '</pubDate>\
  <guid>' + self.tiddlerUrl(t) + '</guid>\
</item>')
	self.response.out.write('\
 </channel>\
</rss>')

  def tiddlerUrl(self, tdlr):
	urlp = self.request.url.split('/')
	urlr = urlp[0] + "//" + urlp[2]
	if tdlr == None:
		return urlr + "/"
	return urlr + tdlr.page + "#" + self.encodeTiddlyLink(tdlr.title)
	
  def encodeTiddlyLink(self, tl):
	try:
		if tl.find(' ') == -1:
			return urllib.quote(tl)
		return urllib.quote('[[' + tl + ']]')
	except KeyError:
		return ""
		
application = webapp.WSGIApplication( [('/index.xml', MainRss)], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
