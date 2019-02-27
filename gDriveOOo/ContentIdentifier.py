#!
# -*- coding: utf_8 -*-

import uno
import unohelper

from com.sun.star.bridge import XInstanceProvider
from com.sun.star.container import XChild
from com.sun.star.io import XInputStreamProvider
from com.sun.star.lang import NoSupportException
from com.sun.star.lang import XServiceInfo
from com.sun.star.ucb.ConnectionMode import OFFLINE
from com.sun.star.ucb.ConnectionMode import ONLINE
from com.sun.star.ucb import IllegalIdentifierException
from com.sun.star.ucb import XContentIdentifier
from com.sun.star.ucb import XContentIdentifierFactory
from com.sun.star.util import XLinkUpdate
from com.sun.star.util import XUpdatable

from gdrive import Initialization
from gdrive import InputStream
from gdrive import PropertySet
from gdrive import createContent
from gdrive import createContentIdentifier
from gdrive import doSync
from gdrive import getItem
from gdrive import getNewIdentifier
from gdrive import getProperty
from gdrive import getSession
from gdrive import getUri
from gdrive import insertJsonItem
from gdrive import isIdentifier
from gdrive import selectChildId
from gdrive import selectItem
from gdrive import updateChildren

from requests.compat import unquote_plus
import traceback

# pythonloader looks for a static g_ImplementationHelper variable
g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationName = 'com.gmail.prrvchr.extensions.gDriveOOo.ContentIdentifier'


class ContentIdentifier(unohelper.Base,
                        XServiceInfo,
                        Initialization,
                        PropertySet,
                        XContentIdentifier,
                        XChild,
                        XInputStreamProvider,
                        XUpdatable,
                        XLinkUpdate,
                        XContentIdentifierFactory,
                        XInstanceProvider):
    def __init__(self, ctx, *namedvalues):
        try:
            self.ctx = ctx
            self.User = None
            self.Uri = None
            self.initialize(namedvalues)
            self.IsNew = self.Uri.hasFragment()
            self._Error = None
            self.Size = 0
            self.MimeType = None
            self.Updated = False
            self.Id, self.Title, self.Url = self._parseUri() if self.User.IsValid else (None, None, None)
            self.Session = getSession(self.ctx, self.Uri.getScheme(), self.User.Name) if self.IsValid else None
        except Exception as e:
            print("ContentIdentifier.__init__().Error: %s - %s" % (e, traceback.print_exc()))

    @property
    def IsRoot(self):
        return self.Id == self.User.RootId
    @property
    def IsValid(self):
        return all((self.Id, self._Error is None))
    @property
    def BaseURL(self):
        return self.Url if self.IsRoot else '%s/%s' % (self.Url, self.Id)
    @property
    def Error(self):
        return self._Error if self.User.Error is None else self.User.Error

    # XInputStreamProvider
    def createInputStream(self):
        return InputStream(self.Session, self.Id, self.Size, self.MimeType)

    # XUpdatable
    def update(self):
        self.Updated = True
        if self.User.Mode == ONLINE:
            with self.Session as session:
                self.Updated = doSync(self.ctx, self.getContentProviderScheme(), self.User.Connection, session, self.User.Id)

    # XLinkUpdate
    def updateLinks(self):
        self.Updated = False
        if self.User.Mode == ONLINE:
            with self.Session as session:
                self.Updated = updateChildren(session, self.User.Connection, self.User.Id, self.Id)

    # XContentIdentifierFactory
    def createContentIdentifier(self, title=''):
        id = getNewIdentifier(self.User.Connection, self.User.Id)
        title = title if title else id
        uri = getUri(self.ctx, '%s/%s#%s' % (self.BaseURL, title, id))
        plugin = 'com.gmail.prrvchr.extensions.gDriveOOo'
        return createContentIdentifier(self.ctx, plugin, self.User, uri)

    # XInstanceProvider
    def getInstance(self, url):
        item = self._getItem()
        if item is not None:
            data = item.get('Data', {})
            mimetype = data.get('MimeType', 'application/octet-stream')
            content = createContent(self.ctx, mimetype, self, data)
            if content is not None:
                return content
            else:
                message = "ERROR: Can't handle mimetype: %s" % mimetype
                self._Error = IllegalIdentifierException(message, self)
        return None

    # XContentIdentifier
    def getContentIdentifier(self):
        return self.Uri.getUriReference()
    def getContentProviderScheme(self):
        return self.Uri.getScheme()

    # XChild
    def getParent(self):
        uri = getUri(self.ctx, self.Url)
        plugin = 'com.gmail.prrvchr.extensions.gDriveOOo'
        return createContentIdentifier(self.ctx, plugin, self.User, uri)
    def setParent(self, parent):
        raise NoSupportException('Parent can not be set', self)

    def _parseUri(self):
        title, position, url = None, -1, None
        parentid, paths = self.User.RootId, []
        for i in range(self.Uri.getPathSegmentCount() -1, -1, -1):
            path = self.Uri.getPathSegment(i).strip()
            if path not in ('','.'):
                if title is None:
                    title = self._unquote(path)
                    position = i
                else:
                    parentid = path
                    break
        if title is None:
            id = self.User.RootId
        elif self.IsNew:
            id = self.Uri.getFragment()
        elif isIdentifier(self.User.Connection, title):
            id = title
        else:
            id = selectChildId(self.User.Connection, parentid, title)
        for i in range(position):
            paths.append(self.Uri.getPathSegment(i).strip())
        if id is None:
            id = self._searchId(paths[::-1], title)
        if id is None:
            message = "ERROR: Can't retrieve Uri: %s" % self.Uri.getUriReference()
            print("contentlib.ContentIdentifier._parseUri() Error: %s" % message)
            self._Error = IllegalIdentifierException(message, self)
        paths.insert(0, self.Uri.getAuthority())
        url = '%s://%s' % (self.Uri.getScheme(), '/'.join(paths))
        return id, title, url

    def _searchId(self, paths, title):
        # Needed for be able to create a folder in a just created folder...
        paths.append(self.User.RootId)
        for index, path in enumerate(paths):
            if isIdentifier(self.User.Connection, path):
                id = path
                break
        for i in range(index -1, -1, -1):
            path = self._unquote(paths[i])
            id = selectChildId(self.User.Connection, id, path)
        id = selectChildId(self.User.Connection, id, title)
        return id

    def _unquote(self, text):
        # Needed for OpenOffice / LibreOffice compatibility
        if isinstance(text, str):
            text = unquote_plus(text)
        else:
            text = unquote_plus(text.encode('utf-8')).decode('utf-8')
        return text

    def _getItem(self):
        item = selectItem(self.User.Connection, self.User.Id, self.Id)
        if item is not None:
            return item
        if self.User.Mode == ONLINE:
            with self.Session as session:
                data = getItem(session, self.Id)
            if data is not None:
                item = insertJsonItem(self.User.Connection, self.User.Id, data)
            else:
                message = "ERROR: Can't retrieve Id from provider: %s" % self.Id
                self._Error = IllegalIdentifierException(message, self)
        else:
            message = "ERROR: Can't retrieve Content: %s Network is Offline" % self.Id
            self._Error = IllegalIdentifierException(message, self)
        return item

    def _getPropertySetInfo(self):
        properties = {}
        maybevoid = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.MAYBEVOID')
        bound = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.BOUND')
        readonly = uno.getConstantByName('com.sun.star.beans.PropertyAttribute.READONLY')
        properties['User'] = getProperty('User', 'com.sun.star.uno.XInterface', maybevoid | bound | readonly)
        properties['Uri'] = getProperty('Uri', 'com.sun.star.uri.XUriReference', bound | readonly)
        properties['Id'] = getProperty('Id', 'string', maybevoid | bound | readonly)
        properties['IsRoot'] = getProperty('IsRoot', 'boolean', bound | readonly)
        properties['IsValid'] = getProperty('IsValid', 'boolean', bound | readonly)
        properties['IsNew'] = getProperty('IsNew', 'boolean', bound | readonly)
        properties['BaseURL'] = getProperty('BaseURL', 'string', bound | readonly)
        properties['Title'] = getProperty('Title', 'string', maybevoid | bound | readonly)
        properties['Updated'] = getProperty('Updated', 'boolean', bound | readonly)
        properties['Size'] = getProperty('Size', 'long', maybevoid | bound)
        properties['MimeType'] = getProperty('MimeType', 'string', maybevoid | bound)
        properties['Error'] = getProperty('Error', 'com.sun.star.ucb.IllegalIdentifierException', maybevoid | bound | readonly)
        return properties

    # XServiceInfo
    def supportsService(self, service):
        return g_ImplementationHelper.supportsService(g_ImplementationName, service)
    def getImplementationName(self):
        return g_ImplementationName
    def getSupportedServiceNames(self):
        return g_ImplementationHelper.getSupportedServiceNames(g_ImplementationName)


g_ImplementationHelper.addImplementation(ContentIdentifier,                                                  # UNO object class
                                         g_ImplementationName,                                               # Implementation name
                                        (g_ImplementationName, ))                                            # List of implemented services
