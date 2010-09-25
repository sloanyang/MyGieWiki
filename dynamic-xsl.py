import cgi
import os.path

from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import memcache

class MainJs(webapp.RequestHandler):
  def get(self):
	path = self.request.path
	epos = path.rfind('/')
	p = path[len('/dynamic/js'):epos]
	s = path[epos + 1:]
	d = memcache.get(p)
	if d != None:
		self.response.out.write(d[s])
	else:
		self.response.set_status(404)

class MainXsl(webapp.RequestHandler):
  def get(self):
	d = memcache.get(self.request.get('path'))
	p = os.path.join(os.path.dirname(__file__),'static','iewiki.xsl')
	ftwd = open('iewiki.xsl')
	text = ftwd.read()
	ftwd.close()
	
	if d != None:
		incls = []
		for (k,v) in d.iteritems():
			incls.append('<script src="/dynamic/js' + self.request.get('path') + "/" + k + '" />')
		self.response.out.write(text.replace('<script src="/static/iewiki.js" />', '<script src="/static/iewiki.js" />\n' + '\n'.join(incls)))
	else:
		self.response.out.write(text);


application = webapp.WSGIApplication( [('/dynamic/iewiki-xsl', MainXsl), ('/dynamic/js/.*', MainJs)], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
