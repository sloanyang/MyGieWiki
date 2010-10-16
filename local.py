# /*************************************
# this:    local.py
# by:    Poul Staugaard
# URL:    http://code.google.com/p/giewiki
# ver.:    1.5.2

# Returns the list of local library pages

from giewikidb import Page

class library:
    def Pages(self,req):
        pages = []
        for p in Page.all().filter('sub',req.subdomain):
            lp = p.path.lower()
            if lp.find('library') >= 0 or lp.find('lib/') >= 0:
                pages.append(p.path)
        return pages
