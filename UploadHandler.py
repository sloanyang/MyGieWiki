# this:  UploadHandler.py
# by:    Poul Staugaard [poul(dot)staugaard(at)gmail...]
# URL:   http://code.google.com/p/giewiki
# ver.:  1.18.0

import logging
import codecs
from google.appengine.api import users
from google.appengine.api import memcache
from google.appengine.ext import webapp
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers

from giewikidb import UploadedFile,Page,UrlImport

def CombinePath(path,fn):
	if path.rfind('/') != len(path) - 1:
		path = path + '/'
	return path + fn

class UploadHandler(blobstore_handlers.BlobstoreUploadHandler):
  def post(self):
	for (a,v) in self.request.POST.items():
		logging.info("UploadH(" + str(a) + ")" + str(v))
	upload_files = self.get_uploads()
	replace = False
	for blob_info in upload_files:
		reqpath = self.request.get('path')
		filename = self.request.get('filename')
		if self.request.get('method') == 'uploadTiddlers':
			url = 'file:' + reqpath + '/' + filename
			logging.info("Uploaded url: " + reqpath + '/' + filename)
			urlimport = UrlImport().all().filter('url',url).get()
			if urlimport == None:
				urlimport = UrlImport()
				urlimport.url = url
			urlimport.blob = blob_info.key()
			urlimport.put()
			self.response.out.write(
'<html>'
'<header><title>Upload succeeded</title>'
'<script>'
'function main() { \n'
'    act = "onUploadTiddlers(' + "'" + url + "'" + ')";'
'    window.parent.setTimeout(act,100);\n'
'}\n'
'</script></header>'
'<body style="margin: 0 0 0 0; text-align: center; font-family: Arial" onload="main()">'
'<center><a href="/">success..</a></center>'
'</body>'
'</html>')
		else:
			f = UploadedFile()
			f.owner = users.get_current_user()
			logging.info("Uploaded " + filename)
			p = filename if filename[0] == '/' else CombinePath(reqpath, filename)
			logging.info('Uploaded ' + p)
			f.path = p
			f.mimetype = blob_info.content_type
			f.blob = blob_info.key()
			ef = UploadedFile.all().filter('path',p).get()
			if ef != None:
				if replace == False:
					msg = p + "&lt;br&gt;is an already existing file - &lt;&lt;confirm_replace " + p + "&gt;&gt;";
					f.msg = msg
					memcache.set(p,f,300)
				elif f.owner != ef.owner and not users.is_current_user_admin():
					msg = "Not allowed"
				else:
					ef.data = f.data
					ef.put()
					msg = p + " replaced"
			elif Page.all().filter("path",p).get():
				msg = p + "&lt;br&gt;is an existing page URL. Pick a different name."
			else:
				msg = ""
				f.put()
			ftwd = codecs.open( 'UploadDialog.htm', 'r', 'utf-8' ) # open('UploadDialog.htm')
			uplurl = blobstore.create_upload_url('/upload')
			text = unicode(ftwd.read()).replace('<uploadHandler>', unicode(uplurl), 1)
			text = text.replace("<requestPath>",reqpath);
			text = text.replace("UFL",unicode(p))
			text = text.replace("UFT",unicode(f.mimetype))
			text = text.replace("ULR",u"Uploaded:")
			text = text.replace("UFM",unicode(msg))
			ftwd.close()
			self.response.out.write(text)
		break

application = webapp.WSGIApplication([('/upload', UploadHandler)], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
