This is (or was) giewiki release 1.15.8.

Starting point:
	http://giewiki.appspot.com (or readme.htm, if present)
 
New features in release 1.15:
	* Site-wide tag links, retrieved via the 'tags' caption.
	* User-defined template for the auto-generated mails.
	* New option to Auto-save changes while editing.
	* Allow custom revision history via the ViewTemplate.
	* On demand-loading macro's assuming tiddler title = '<macro-name> macro'.
	* Lazy-load tiddler attribute for generel load-on-demand.
	* "requires" attribute for systemConfig tiddlers.
	* Admin now has direct DataStore link to http://appengine.google.com.
	* NoAccessMessage, a special tiddler, which prompts the user to log in if he doesn't have (anonymous) read-access to the page. 
	  It's therefore listed in stead of the defined DefaultTiddlers in such case.

New in 1.15.8:
	* Tiddler fields can now be added, edited & deleted (by clearing the value) via a dialog available to admins through the 'fields' popup.
	  This allows selecting an alternative "viewtemplate" and/or "edittemplate" for a tiddler, or defining the "requires" attribute of a systemConfig tiddler.
	* When Moving a page to a different URL, you now have the option to set up a redirect of the current URL to the new.
	* Whether to show the tiddler byline in read-only mode is now a page property.

Additional resources:
	http://code.google.com/p/giewiki

Enjoy!