This is (or was) giewiki release 1.16.0.

Starting point:
	http://giewiki.appspot.com

New features in release 1.16:
	* The attribute tag tiddlerTemplate marks a tiddler as template for editing or viewing tiddlers.
	  A new macro <<tiwinate>>, used in EditingMenu lets you easily subclass the existing EditTemplate and ViewTemplate tiddlers 
	  by defining (copy via page setup - All..) derivatives named e.g. thingEditTemplate and thingEditTemplate. This will produce
	  a new entry in the edit sidebar labeled (in this case) "new thing".
	* When you have a tiddler tagged tiddlerTemplate, a link pattern of the form templateName/tiddlerName will render tiddlerName
	  using templateName as the HTML template.
	* You can now paste a tiddler on the same page as where you did the copy (via the editing menu). This will produce a copy where
	  the title is derived by prepending a '_'.
 
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

Feedback:
	http://giewiki.appspot.com/FeedBack
	poul.staugaard@gmail.com

Enjoy!